"""GTK4 plugin menu adapter.

Allows GTK3-era plugins (capability 'terminal_menu') that expect to receive
Gtk.Menu and Gtk.MenuItem objects to populate a menu, by providing lightweight
"fake" menu/item objects and then converting the results into a Gio.MenuModel
with SimpleActions installed on the terminal's action group.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple, Any, Dict
from gi.repository import Gio, GLib

from .plugin import PluginRegistry


class FakeMenu:
    def __init__(self):
        self.items: List[FakeMenuItem] = []

    def append(self, item: 'FakeMenuItem'):
        self.items.append(item)

    # Compatibility with Gtk.Menu API used by some plugins
    def get_children(self):
        return list(self.items)


class FakeMenuItem:
    def __init__(self, label: str):
        self.label = label
        self.submenu: Optional[FakeMenu] = None
        self._activate_cbs: List[Tuple[Callable, tuple]] = []
        self.separator = False

    # Factory constructors used by plugins
    @classmethod
    def new_with_mnemonic(cls, label: str) -> 'FakeMenuItem':
        return cls(label)

    @classmethod
    def new_with_label(cls, label: str) -> 'FakeMenuItem':
        return cls(label)

    # API surface used by plugins
    def connect(self, signal: str, func: Callable, *args):
        if signal == 'activate':
            self._activate_cbs.append((func, args))
        return None

    # Some plugins use connect_after; treat as connect for our purposes
    def connect_after(self, signal: str, func: Callable, *args):
        return self.connect(signal, func, *args)

    def set_submenu(self, submenu: FakeMenu):
        self.submenu = submenu

    # No-op compatibility methods
    def set_property(self, *args, **kwargs):
        pass

    def set_image(self, *args, **kwargs):
        pass

    def set_always_show_image(self, *args, **kwargs):
        pass

    # Minimal getters used by plugins for filtering or display
    def get_label(self) -> str:
        return self.label


class FakeSeparatorMenuItem(FakeMenuItem):
    def __init__(self):
        super().__init__('')
        self.separator = True


class FakeCheckMenuItem(FakeMenuItem):
    def __init__(self, label: str, active: bool = False):
        super().__init__(label)
        self._active = bool(active)
        self._toggled_cbs: List[Tuple[Callable, tuple]] = []

    @classmethod
    def new_with_mnemonic(cls, label: str) -> 'FakeCheckMenuItem':
        return cls(label, False)

    @classmethod
    def new_with_label(cls, label: str) -> 'FakeCheckMenuItem':
        return cls(label, False)

    def set_active(self, active: bool):
        self._active = bool(active)

    def get_active(self) -> bool:
        return self._active

    def connect(self, signal: str, func: Callable, *args):
        if signal == 'toggled':
            self._toggled_cbs.append((func, args))
            return None
        return super().connect(signal, func, *args)


class FakeRadioMenuItem(FakeMenuItem):
    def __init__(self, label: str):
        super().__init__(label)
        self._toggled_cbs: List[Tuple[Callable, tuple]] = []
        self._group_id: Optional[int] = None
        self._active: bool = False
        self._value: Optional[str] = None

    @classmethod
    def new_with_mnemonic(cls, label: str) -> 'FakeRadioMenuItem':
        return cls(label)

    @classmethod
    def new_with_label(cls, label: str) -> 'FakeRadioMenuItem':
        return cls(label)

    def set_group(self, group):
        # We don't maintain linked objects; just tag with a numeric id
        self._group_id = id(group)

    def connect(self, signal: str, func: Callable, *args):
        if signal == 'toggled':
            self._toggled_cbs.append((func, args))
            return None
        return super().connect(signal, func, *args)

    def set_active(self, active: bool):
        self._active = bool(active)

    def get_active(self) -> bool:
        return self._active

    def set_value(self, value: str):
        self._value = value
        return self

    def get_value(self) -> str:
        # Default to label if not set
        return self._value if self._value is not None else self.label


def _slug(label: str) -> str:
    return ''.join(ch.lower() if ch.isalnum() else '-' for ch in label).strip('-') or 'item'


def _build_gio_menu_from_fake(menu: FakeMenu, terminal, action_prefix: str,
                              action_sink: List[Tuple[str, Any]]):
    gio_menu = Gio.Menu()
    # Build as sections split by separators
    section = Gio.Menu()
    idx = 0
    def flush_section():
        nonlocal section
        # Append section only if it has items
        if section.get_n_items() > 0:
            gio_menu.append_section(None, section)
        section = Gio.Menu()

    # Collect radio groups in the current section to batch into one stateful action per group
    radio_groups: Dict[int, List[FakeRadioMenuItem]] = {}

    for item in menu.items:
        if getattr(item, 'separator', False):
            # Before flushing section, insert any pending radio groups
            for gid, items in radio_groups.items():
                _append_radio_group(section, items, f"{action_prefix}-radio-{gid}", action_sink)
            radio_groups.clear()
            flush_section()
            continue
        if item.submenu:
            # Recurse
            sub = _build_gio_menu_from_fake(item.submenu, terminal,
                                            f"{action_prefix}-{idx}", action_sink)
            section.append_submenu(item.label, sub)
        else:
            act_name = f"{action_prefix}-{_slug(item.label)}-{idx}"
            # Radio item: enqueue into its group, to be added as a single stateful action
            if isinstance(item, FakeRadioMenuItem):
                gid = item._group_id or (0xBEEF << 16) + idx  # stable-ish fallback
                radio_groups.setdefault(gid, []).append(item)
            elif isinstance(item, FakeCheckMenuItem):
                # Define change-state callback that flips active and dispatches callbacks
                def make_change_state(it: FakeCheckMenuItem):
                    def _on_change(action, value):
                        try:
                            new_val = value.get_boolean() if value is not None else (not it.get_active())
                        except Exception:
                            new_val = not it.get_active()
                        it.set_active(new_val)
                        # Emit toggled callbacks first
                        for func, args in list(getattr(it, '_toggled_cbs', [])):
                            try:
                                # Provide a widget-like object with get_active()
                                func(it, *args)
                            except TypeError:
                                try:
                                    func(it)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        # Then activate callbacks
                        for func, args in list(getattr(it, '_activate_cbs', [])):
                            try:
                                func(None, *args)
                            except TypeError:
                                try:
                                    func(None)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        try:
                            action.set_state(GLib.Variant('b', new_val))
                        except Exception:
                            pass
                    return _on_change

                action_sink.append((act_name, 'toggle', bool(item.get_active()), make_change_state(item)))
                mitem = Gio.MenuItem.new(item.label, None)
                # It’s enough to bind to the action; boolean state makes it checkable
                mitem.set_attribute_value('action', GLib.Variant('s', f'term.{act_name}'))
                section.append_item(mitem)
            else:
                # Simple action
                def make_cb(cbs):
                    def _runner(_action, _param):
                        for func, args in cbs:
                            try:
                                func(None, *args)
                            except TypeError:
                                try:
                                    func(None)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    return _runner
                action_sink.append((act_name, 'simple', make_cb(item._activate_cbs)))
                mitem = Gio.MenuItem.new(item.label, None)
                mitem.set_attribute_value('action', GLib.Variant('s', f'term.{act_name}'))
                section.append_item(mitem)
        idx += 1
    # Append any remaining radio groups at end of section
    for gid, items in radio_groups.items():
        _append_radio_group(section, items, f"{action_prefix}-radio-{gid}", action_sink)
    flush_section()
    return gio_menu


def _append_radio_group(section: Gio.Menu, items: List[FakeRadioMenuItem], action_name: str,
                        action_sink: List[Tuple[str, Any]]):
    # Determine initial state (first active, else first item)
    initial = None
    for it in items:
        if it.get_active():
            initial = it.get_value()
            break
    if initial is None and items:
        initial = items[0].get_value()

    # Change-state callback dispatches toggled/activate for selected radio item
    def on_change(action, value):
        try:
            new_val = value.get_string() if value is not None else initial
        except Exception:
            new_val = initial
        # Set active flags accordingly and fire callbacks
        for it in items:
            active = (it.get_value() == new_val)
            it.set_active(active)
            if active:
                for func, args in list(getattr(it, '_toggled_cbs', [])):
                    try:
                        func(it, *args)
                    except TypeError:
                        try:
                            func(it)
                        except Exception:
                            pass
                    except Exception:
                        pass
                for func, args in list(getattr(it, '_activate_cbs', [])):
                    try:
                        func(None, *args)
                    except TypeError:
                        try:
                            func(None)
                        except Exception:
                            pass
                    except Exception:
                        pass
        try:
            action.set_state(GLib.Variant('s', str(new_val)))
        except Exception:
            pass

    # Register radio action
    action_sink.append((action_name, 'radio', str(initial or ''), on_change))
    # Add each item as a menu entry targeting this stateful action
    for it in items:
        mitem = Gio.MenuItem.new(it.label, None)
        mitem.set_attribute_value('action', GLib.Variant('s', f'term.{action_name}'))
        mitem.set_attribute_value('target', GLib.Variant('s', it.get_value()))
        section.append_item(mitem)


def build_plugin_menu_for_terminal(terminal) -> Tuple[Optional[Gio.MenuModel], List[Tuple[str, Any]]]:
    """Collect plugin menu items and convert to Gio.MenuModel and action list.

    Returns (menu_model, actions). actions is a list of (action_name, callback)
    to be installed on the terminal's SimpleActionGroup as 'term.<action_name>'.
    """
    try:
        registry = PluginRegistry()
        registry.load_plugins()
        plugins = registry.get_plugins_by_capability('terminal_menu')
    except Exception:
        plugins = []

    collector = FakeMenu()
    items: List[FakeMenuItem] = []

    # Ask all plugins to populate using GTK shims to capture GTK3 MenuItems
    # and CheckMenuItems into our Fake structures.
    def _patch_gtk_for_callback() -> tuple:
        # Build a small shim overlay on gi.repository.Gtk for menu APIs
        import gi
        from gi.repository import Gtk as RealGtk

        class Image:
            def set_from_icon_name(self, *args, **kwargs):
                pass

        class IconTheme:
            @staticmethod
            def get_default():
                return IconTheme()
            def choose_icon(self, *args, **kwargs):
                return None

        class GtkShim:
            Menu = FakeMenu
            MenuItem = FakeMenuItem
            ImageMenuItem = FakeMenuItem
            SeparatorMenuItem = FakeSeparatorMenuItem
            CheckMenuItem = FakeCheckMenuItem
            RadioMenuItem = FakeRadioMenuItem
            Image = Image
            class IconSize:
                MENU = 0
            class IconLookupFlags:
                USE_BUILTIN = 0

        # Save originals to restore later
        saved = {}
        for name in ('Menu','MenuItem','ImageMenuItem','SeparatorMenuItem','CheckMenuItem','RadioMenuItem','Image','IconTheme','IconSize','IconLookupFlags'):
            saved[name] = getattr(RealGtk, name, None)
        # Apply
        RealGtk.Menu = GtkShim.Menu
        RealGtk.MenuItem = GtkShim.MenuItem
        RealGtk.ImageMenuItem = GtkShim.ImageMenuItem
        RealGtk.SeparatorMenuItem = GtkShim.SeparatorMenuItem
        RealGtk.CheckMenuItem = GtkShim.CheckMenuItem
        RealGtk.RadioMenuItem = GtkShim.RadioMenuItem
        RealGtk.Image = GtkShim.Image
        RealGtk.IconTheme = IconTheme
        RealGtk.IconSize = GtkShim.IconSize
        RealGtk.IconLookupFlags = GtkShim.IconLookupFlags
        return RealGtk, saved

    def _restore_gtk(real_gtk, saved):
        for name, val in saved.items():
            try:
                if val is None:
                    delattr(real_gtk, name)
                else:
                    setattr(real_gtk, name, val)
            except Exception:
                pass

    for plugin in plugins:
        # Patch GTK types only around the callback
        try:
            RealGtk, saved = _patch_gtk_for_callback()
            try:
                plugin.callback(items, collector, terminal)
            finally:
                _restore_gtk(RealGtk, saved)
        except Exception:
            continue

    # If plugins added directly to list, append them to the collector
    for it in items:
        if isinstance(it, FakeMenuItem):
            collector.append(it)
        elif getattr(it, '__class__', None).__name__ == 'SeparatorMenuItem':
            collector.append(FakeSeparatorMenuItem())

    if not collector.items:
        return None, []

    actions: List[Tuple[str, Any]] = []
    menu_model = _build_gio_menu_from_fake(collector, terminal, 'plugin', actions)
    return menu_model, actions
