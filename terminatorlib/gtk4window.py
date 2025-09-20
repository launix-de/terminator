"""Minimal GTK4 Window hosting a single VTE terminal.

This is a stepping stone toward a full GTK4 port. It purposefully
implements only a small subset of behaviors so we can iterate.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk, GLib, Gdk
from .translation import _

from .gtk4terminal import Gtk4Terminal
from .gtk4titlebar import Gtk4Titlebar


class TerminatorGtk4Window(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("Terminator")
        self.set_default_size(1000, 700)
        self.root = None
        self._group_counter = 0
        self._uuid_unit_map = {}
        self._install_shortcuts()
        self._force_close = False
        # Intercept close to optionally confirm
        try:
            self.connect('close-request', self._on_close_request)
        except Exception:
            pass
        # Install CSS for GTK4 theming (load from file if available, else minimal defaults)
        try:
            prov = Gtk.CssProvider()
            css_loaded = False
            try:
                import os as _os
                _path = _os.path.join(_os.path.dirname(__file__), 'themes', 'gtk-4.0', 'terminator.css')
                if _os.path.exists(_path):
                    with open(_path, 'rb') as f:
                        prov.load_from_data(f.read())
                        css_loaded = True
            except Exception:
                pass
            if not css_loaded:
                css = b"""
                .term-titlebar.tx { background-color: alpha(@theme_selected_bg_color, 0.35); }
                .term-titlebar.rx { background-color: alpha(@theme_selected_bg_color, 0.15); }
                .term-titlebar.inactive { background-color: transparent; }
                .term-titlebar { padding: 2px 6px; }
                .dim-label { opacity: 0.7; }
                """
                prov.load_from_data(css)
            disp = Gdk.Display.get_default()
            if disp is not None:
                Gtk.StyleContext.add_provider_for_display(disp, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            # Keep a provider for dynamic titlebar color/font overrides from Config
            self._title_css_provider = Gtk.CssProvider()
            if disp is not None:
                Gtk.StyleContext.add_provider_for_display(disp, self._title_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:
            pass
        # Initialize window hints and broadcast_default from config
        try:
            from .config import Config
            cfg = Config()
            # Always on top / hide from taskbar where supported
            try:
                if hasattr(self, 'set_keep_above'):
                    self.set_keep_above(bool(cfg['always_on_top']))
            except Exception:
                pass
            try:
                if hasattr(self, 'set_skip_taskbar_hint'):
                    self.set_skip_taskbar_hint(bool(cfg['hide_from_taskbar']))
            except Exception:
                pass
            bd = (cfg['broadcast_default'] or 'group').lower()
            if bd in ('all', 'group', 'off'):
                self._set_groupsend(bd)
        except Exception:
            pass

        # Hide on lose focus
        try:
            def on_notify_is_active(win, _pspec):
                try:
                    from .config import Config as _Cfg
                    if not win.get_property('is-active') and bool(_Cfg()['hide_on_lose_focus']):
                        win.hide()
                except Exception:
                    pass
            # 'is-active' is a property on Gtk.Window that changes with focus
            self.connect('notify::is-active', on_notify_is_active)
        except Exception:
            pass

        # Layout: simple box with one terminal for now
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_hexpand(True)
        root.set_vexpand(True)
        self.set_child(root)
        self.root = root

        term, container = self._new_terminal_container()
        self.term = term
        # In Gtk4, append replaces pack_* and add
        root.append(container)

        # Close window when the child exits
        term.connect("child-exited", self.on_child_exited)

        # Spawn user's shell
        term.spawn_login_shell()
        # Apply titlebar style overrides from config on startup
        try:
            self.refresh_titlebar_style()
        except Exception:
            pass

    def on_child_exited(self, term, status):
        # If there are multiple terminals, remove just this one; else close
        scroller = term.get_parent()
        unit = scroller.get_parent()  # our terminal container (titlebar + scroller)
        parent = unit.get_parent()
        def terminals_remain():
            try:
                return self._count_terminals_in(self.get_child()) > 0
            except Exception:
                return False
        if isinstance(parent, Gtk.Paned):
            # Identify the sibling to keep
            if parent.get_end_child() is unit:
                other = parent.get_start_child()
                parent.set_start_child(None)
                parent.set_end_child(None)
            else:
                other = parent.get_end_child()
                parent.set_end_child(None)
                parent.set_start_child(None)

            grand = parent.get_parent()

            if isinstance(grand, Gtk.Paned):
                # Replace the container in its grandparent paned slot
                if grand.get_start_child() is parent:
                    grand.set_start_child(other)
                else:
                    grand.set_end_child(other)
            elif isinstance(grand, Gtk.Box):
                # Keep ordering by inserting after the previous sibling
                prev = None
                child = grand.get_first_child()
                while child is not None and child is not parent:
                    prev = child
                    child = child.get_next_sibling()
                grand.remove(parent)
                if prev is None:
                    grand.prepend(other)
                else:
                    grand.insert_child_after(other, prev)
            elif isinstance(grand, Gtk.Notebook):
                # Replace the page content with 'other'
                idx = -1
                for i in range(grand.get_n_pages()):
                    if grand.get_nth_page(i) is parent:
                        idx = i
                        break
                if idx >= 0:
                    label = grand.get_tab_label(grand.get_nth_page(idx))
                    grand.remove_page(idx)
                    grand.insert_page(other, label, idx)
                    grand.set_current_page(idx)
            # If any terminals remain, don't close the window
            if terminals_remain():
                return
        elif isinstance(parent, Gtk.Notebook):
            # Remove just this tab; keep window open if other tabs remain
            idx = -1
            for i in range(parent.get_n_pages()):
                if parent.get_nth_page(i) is unit:
                    idx = i
                    break
            if idx >= 0:
                parent.remove_page(idx)
                n = parent.get_n_pages()
                if n > 0:
                    parent.set_current_page(min(idx, n - 1))
                    return
            # If no tabs remain, close the window
            try:
                self.close()
            except Exception:
                pass
        else:
            # Not inside a Paned or Notebook (single view). Close the window.
            try:
                if isinstance(parent, Gtk.Box):
                    try:
                        parent.remove(unit)
                    except Exception:
                        pass
                    if terminals_remain():
                        return
                self.close()
            except Exception:
                pass

    def _new_terminal_container(self):
        from .config import Config
        cfg = Config()
        term = Gtk4Terminal()
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_child(term)
        term.set_hexpand(True)
        term.set_vexpand(True)
        term.set_scroller(scroller)
        term.connect("child-exited", self.on_child_exited)
        term.spawn_login_shell()

        # Titlebar container with controls
        titlebar = Gtk4Titlebar(self, None)  # unit set after unit is constructed
        # Connect titlebar group creation to set group on this unit
        def on_create_group(tb, name):
            self._set_unit_group(unit, name or None)
        titlebar.connect('create-group', on_create_group)

        # Container holding titlebar + scroller
        unit = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        unit.set_hexpand(True)
        unit.set_vexpand(True)
        # Show/hide titlebar per config
        if not cfg['show_titlebar']:
            titlebar.hide()
        # Now titlebar can know its unit container
        titlebar._unit = unit
        # Position titlebar per preference
        try:
            if bool(cfg['title_at_bottom']):
                unit.append(scroller)
                unit.append(titlebar)
            else:
                unit.append(titlebar)
                unit.append(scroller)
        except Exception:
            unit.append(titlebar)
            unit.append(scroller)

        return term, unit

    # Find the tab label widget for the notebook page that contains the given unit
    def _rename_tab_for_unit(self, unit: Gtk.Widget):
        notebook, page_idx = self._find_notebook_page_for_widget(unit)
        if notebook is None or page_idx < 0:
            # Fallback: use dialog
            self._on_edit_tab_title()
            return
        page = notebook.get_nth_page(page_idx)
        label = notebook.get_tab_label(page)
        # If label is a plain Gtk.Label, wrap it using our factory to enable double-click renaming later
        if isinstance(label, Gtk.Label):
            new_widget = self._make_tab_label_widget(label.get_label() or str(page_idx+1), page)
            notebook.set_tab_label(page, new_widget)
            label = new_widget
        # Anchor rename popover to the tab label widget
        self._show_tab_rename_popover(label, page)

    def _find_notebook_page_for_widget(self, widget: Gtk.Widget):
        # Walk up to find notebook, then find page index whose content contains widget
        w = widget
        # First locate the notebook ancestor
        nb = None
        while w is not None:
            parent = w.get_parent()
            if isinstance(parent, Gtk.Notebook):
                nb = parent
                break
            w = parent
        if nb is None:
            return None, -1
        # Find page index containing the original widget
        for i in range(nb.get_n_pages()):
            page = nb.get_nth_page(i)
            if self._widget_contains(page, widget):
                return nb, i
        return nb, -1

    def _widget_contains(self, container: Gtk.Widget, target: Gtk.Widget) -> bool:
        if container is target:
            return True
        if isinstance(container, Gtk.Box):
            child = container.get_first_child()
            while child is not None:
                if self._widget_contains(child, target):
                    return True
                child = child.get_next_sibling()
        elif isinstance(container, Gtk.Paned):
            for ch in (container.get_start_child(), container.get_end_child()):
                if ch is not None and self._widget_contains(ch, target):
                    return True
        return False

    # Grouping helpers (window-local)
    def _set_unit_group(self, unit: Gtk.Widget, name: str | None):
        # Update titlebar label and store group on terminals in this unit
        from .terminator import Terminator
        term = self._find_terminal_in_container(unit)
        if term is None:
            return
        # Create group in global registry if named
        if name:
            try:
                Terminator().create_group(name)
            except Exception:
                pass
        # Update titlebar display
        tb = unit.get_first_child() if isinstance(unit, Gtk.Box) else None
        if isinstance(tb, Gtk.Box):
            # try to call our widget API
            if hasattr(tb, '_group_label'):
                try:
                    tb._group_label.set_label(name or '')
                except Exception:
                    pass
            # Update broadcast icon for this unit
            if hasattr(self, '_update_broadcast_for_unit'):
                self._update_broadcast_for_unit(unit)
            # Update active RX/TX state as membership changed
            try:
                self._update_active_states()
            except Exception:
                pass
        # Stash group on terminal for navigation/visuals
        try:
            setattr(term, '_group', name)
        except Exception:
            pass

    def _iter_units_in_container(self, container: Gtk.Widget):
        # Yield unit containers (vertical Boxes with term-titlebar class first child)
        if isinstance(container, Gtk.Box):
            first = container.get_first_child()
            if isinstance(first, Gtk.Box) and 'term-titlebar' in first.get_css_classes():
                yield container
            child = container.get_first_child()
            while child is not None:
                yield from self._iter_units_in_container(child)
                child = child.get_next_sibling()
        elif isinstance(container, Gtk.Paned):
            for ch in (container.get_start_child(), container.get_end_child()):
                if ch is not None:
                    yield from self._iter_units_in_container(ch)

    def _group_all_window(self, _caller_term=None):
        # Create a window-wide group and assign to all units
        self._group_counter += 1
        name = f"Window group {self._group_counter}"
        root = self.get_child()
        for unit in self._iter_units_in_container(root):
            self._set_unit_group(unit, name)
        if hasattr(self, '_update_broadcast_icons'):
            self._update_broadcast_icons()
        try:
            self._update_active_states()
        except Exception:
            pass

    def _ungroup_all_window(self, _caller_term=None):
        root = self.get_child()
        for unit in self._iter_units_in_container(root):
            self._set_unit_group(unit, None)
        if hasattr(self, '_update_broadcast_icons'):
            self._update_broadcast_icons()
        try:
            self._update_active_states()
        except Exception:
            pass

    def _group_all_tab(self, caller_term=None):
        nb = self.get_child() if isinstance(self.get_child(), Gtk.Notebook) else None
        if nb is None:
            return
        idx = nb.get_current_page()
        if idx < 0:
            return
        page = nb.get_nth_page(idx)
        self._group_counter += 1
        name = f"Tab {idx+1}"
        for unit in self._iter_units_in_container(page):
            self._set_unit_group(unit, name)
        if hasattr(self, '_update_broadcast_icons'):
            self._update_broadcast_icons()
        try:
            self._update_active_states()
        except Exception:
            pass

    def _ungroup_all_tab(self, caller_term=None):
        nb = self.get_child() if isinstance(self.get_child(), Gtk.Notebook) else None
        if nb is None:
            return
        idx = nb.get_current_page()
        if idx < 0:
            return
        page = nb.get_nth_page(idx)
        for unit in self._iter_units_in_container(page):
            self._set_unit_group(unit, None)
        if hasattr(self, '_update_broadcast_icons'):
            self._update_broadcast_icons()
        try:
            self._update_active_states()
        except Exception:
            pass

    def _set_groupsend(self, mode: str):
        # mode in {'off','group','all'}
        from .terminator import Terminator
        t = Terminator()
        mapping = t.groupsend_type if hasattr(t, 'groupsend_type') else {'all':0,'group':1,'off':2}
        if mode in mapping:
            try:
                t.groupsend = mapping[mode]
            except Exception:
                pass
        # Update broadcast icons
        try:
            self._update_broadcast_icons()
        except Exception:
            pass
        try:
            self._update_active_states()
        except Exception:
            pass

    def _on_terminal_focus_changed(self, term, focused: bool):
        # Recompute active/transmit/receive states when focus changes
        try:
            self._update_active_states()
        except Exception:
            pass

    def _update_active_states(self):
        # Determine current broadcast mode and focused unit's group
        from .terminator import Terminator
        t = Terminator()
        try:
            rev = {v:k for k,v in t.groupsend_type.items()}
            mode = rev.get(getattr(t, 'groupsend', t.groupsend_type.get('off')), 'off')
        except Exception:
            mode = 'off'
        focused = self._get_focused_terminal()
        focused_group = getattr(focused, '_group', None) if focused is not None else None
        # Iterate units and set titlebar class accordingly
        root = self.get_child()
        if root is None:
            return
        for unit in self._iter_units_in_container(root):
            term = self._find_terminal_in_container(unit)
            tb = unit.get_first_child() if isinstance(unit, Gtk.Box) else None
            if not hasattr(tb, 'set_active_state'):
                continue
            if term is focused:
                tb.set_active_state('tx')
            else:
                rx = False
                if mode == 'all':
                    rx = True
                elif mode == 'group':
                    rx = getattr(term, '_group', None) is not None and getattr(term, '_group', None) == focused_group
                tb.set_active_state('rx' if rx else 'inactive')

    def _update_broadcast_icons(self):
        # Update all units based on current groupsend mode and membership
        root = self.get_child()
        if root is None:
            return
        for unit in self._iter_units_in_container(root):
            self._update_broadcast_for_unit(unit)

    def _update_broadcast_for_unit(self, unit):
        # mode from Terminator, membership from terminal's _group attr
        from .terminator import Terminator
        t = Terminator()
        mode = 'off'
        try:
            rev = {v:k for k,v in t.groupsend_type.items()}
            mode = rev.get(getattr(t, 'groupsend', t.groupsend_type.get('off')), 'off')
        except Exception:
            pass
        term = self._find_terminal_in_container(unit)
        name = getattr(term, '_group', None) if term is not None else None
        tb = unit.get_first_child() if isinstance(unit, Gtk.Box) else None
        if hasattr(tb, 'set_broadcast_state'):
            try:
                tb.set_broadcast_state(mode, bool(name))
            except Exception:
                pass

    def _install_shortcuts(self):
        # Install configurable shortcuts mapped from Config keybindings
        from .config import Config
        cfg = Config()

        def add_shortcut(trigger_str, callback):
            if not trigger_str:
                return
            trig = Gtk.ShortcutTrigger.parse_string(trigger_str.replace('Primary', 'Control'))
            if not trig:
                return
            ctrl = Gtk.ShortcutController()
            # Ensure shortcuts work even when a child (e.g., VTE) has focus
            try:
                ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
            except Exception:
                pass
            try:
                ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            except Exception:
                pass
            ctrl.add_shortcut(Gtk.Shortcut.new(trig, Gtk.CallbackAction.new(callback)))
            self.add_controller(ctrl)

        # Map keybinding names to callbacks
        mapping = {
            'next_tab': self._on_tab_next,
            'prev_tab': self._on_tab_prev,
            'cycle_next': lambda *a: self._on_cycle_focus(1),
            'cycle_prev': lambda *a: self._on_cycle_focus(-1),
            'new_tab': self._on_new_tab,
            'split_horiz': lambda *a: self._on_split(Gtk.Orientation.HORIZONTAL),
            'split_vert': lambda *a: self._on_split(Gtk.Orientation.VERTICAL),
            'split_auto': self._on_split_auto,
            'find_next': lambda *a: self._on_find(True),
            'find_previous': lambda *a: self._on_find(False),
            'go_up': lambda *a: self._on_focus_direction('up'),
            'go_down': lambda *a: self._on_focus_direction('down'),
            'go_left': lambda *a: self._on_focus_direction('left'),
            'go_right': lambda *a: self._on_focus_direction('right'),
            'close_window': self._on_close_window,
            'close_term': self._on_close_term,
            'copy': self._on_copy,
            'paste': self._on_paste,
            'paste_selection': self._on_paste_selection,
            'copy_html': self._on_copy_html,
            'search': self._on_search,
            'zoom_in': self._on_zoom_in,
            'zoom_out': self._on_zoom_out,
            'zoom_normal': self._on_zoom_normal,
            'toggle_scrollbar': self._on_toggle_scrollbar,
            'full_screen': self._on_full_screen,
            'new_window': self._on_new_window,
            'hide_window': self._on_hide_window,
            'preferences_keybindings': self._on_preferences,
            'preferences': self._on_preferences,
            'edit_window_title': self._on_edit_window_title,
            'edit_tab_title': self._on_edit_tab_title,
            'layout_launcher': self._on_layout_launcher,
            'new_terminator': self._on_new_window,
            # Grouping/broadcast keybindings
            'create_group': lambda *a: self._on_create_group(),
            'group_all': lambda *a: self._group_all_window(),
            'group_all_toggle': lambda *a: self._on_group_all_toggle(),
            'ungroup_all': lambda *a: self._ungroup_all_window(),
            'group_win': lambda *a: self._group_all_window(),
            'group_win_toggle': lambda *a: self._on_group_all_toggle(),
            'ungroup_win': lambda *a: self._ungroup_all_window(),
            'group_tab': lambda *a: self._group_all_tab(),
            'group_tab_toggle': lambda *a: self._on_group_tab_toggle(),
            'ungroup_tab': lambda *a: self._ungroup_all_tab(),
            'broadcast_off': lambda *a: self._set_groupsend('off'),
            'broadcast_group': lambda *a: self._set_groupsend('group'),
            'broadcast_all': lambda *a: self._set_groupsend('all'),
            'move_tab_right': lambda *a: self._on_move_tab(1),
            'move_tab_left': lambda *a: self._on_move_tab(-1),
            'next_profile': lambda *a: self._on_cycle_profile(1),
            'previous_profile': lambda *a: self._on_cycle_profile(-1),
            'reset': self._on_reset_terminal,
            'reset_clear': self._on_reset_clear_terminal,
            'help': self._on_help,
            'resize_up': lambda *a: self._on_resize_direction('up'),
            'resize_down': lambda *a: self._on_resize_direction('down'),
            'resize_left': lambda *a: self._on_resize_direction('left'),
            'resize_right': lambda *a: self._on_resize_direction('right'),
            # Tab switching 1..10
            'switch_to_tab_1': lambda *a: self._on_switch_to_tab(0),
            'switch_to_tab_2': lambda *a: self._on_switch_to_tab(1),
            'switch_to_tab_3': lambda *a: self._on_switch_to_tab(2),
            'switch_to_tab_4': lambda *a: self._on_switch_to_tab(3),
            'switch_to_tab_5': lambda *a: self._on_switch_to_tab(4),
            'switch_to_tab_6': lambda *a: self._on_switch_to_tab(5),
            'switch_to_tab_7': lambda *a: self._on_switch_to_tab(6),
            'switch_to_tab_8': lambda *a: self._on_switch_to_tab(7),
            'switch_to_tab_9': lambda *a: self._on_switch_to_tab(8),
            'switch_to_tab_10': lambda *a: self._on_switch_to_tab(9),
            # Scrolling
            'page_up': lambda *a: self._on_scroll_page(-1),
            'page_down': lambda *a: self._on_scroll_page(1),
            'page_up_half': lambda *a: self._on_scroll_page(-0.5),
            'page_down_half': lambda *a: self._on_scroll_page(0.5),
            'line_up': lambda *a: self._on_scroll_line(-1),
            'line_down': lambda *a: self._on_scroll_line(1),
        }

        for key, callback in mapping.items():
            add_shortcut(cfg['keybindings'].get(key), callback)

    def _on_find(self, forward: bool):
        term = self._get_focused_terminal()
        if term is None:
            return True
        # Use terminal's actions if available
        try:
            if forward and hasattr(term, '_search_find'):
                term._search_find(True)
            elif not forward and hasattr(term, '_search_find'):
                term._search_find(False)
        except Exception:
            pass
        return True

    def _update_title_for_terminal(self, term, title: str):
        # Update titlebar label and tab label for the unit containing this terminal
        scroller = term.get_parent()
        if scroller is None:
            return
        unit = scroller.get_parent()
        # Update the titlebar text
        tb = unit.get_first_child() if isinstance(unit, Gtk.Box) else None
        if isinstance(tb, Gtk.Box) and 'term-titlebar' in tb.get_css_classes():
            # Titlebar is our custom widget; try to set its label if method exists
            if hasattr(tb, 'set_title'):
                try:
                    tb.set_title(title)
                except Exception:
                    pass
            else:
                # Fallback: find label child
                child = tb.get_first_child()
                while child is not None:
                    if isinstance(child, Gtk.Label):
                        child.set_label(title)
                        break
                    child = child.get_next_sibling()
        # Update tab label text if inside a notebook
        nb, idx = self._find_notebook_page_for_widget(unit)
        if nb is not None and idx >= 0:
            page = nb.get_nth_page(idx)
            lbl = nb.get_tab_label(page)
            updated = False
            if isinstance(lbl, Gtk.Box):
                # Find first Gtk.Label child and update it
                c = lbl.get_first_child()
                while c is not None:
                    if isinstance(c, Gtk.Label):
                        c.set_label(title)
                        updated = True
                        break
                    c = c.get_next_sibling()
            elif isinstance(lbl, Gtk.Label):
                lbl.set_label(title)
                updated = True
            # Fallback: if we couldn't update custom label, try using convenience API
            if not updated:
                try:
                    if hasattr(nb, 'set_tab_label_text'):
                        nb.set_tab_label_text(page, title)
                except Exception:
                    pass

    def refresh_shortcuts(self):
        # Remove all existing ShortcutControllers and reinstall from Config
        controllers = [c for c in self.observe_controllers()]
        for c in controllers:
            if isinstance(c, Gtk.ShortcutController):
                self.remove_controller(c)
        self._install_shortcuts()

    def refresh_titlebars(self, visible: bool):
        # Walk all terminal unit containers in the window and show/hide their titlebars
        def process_container(container):
            if isinstance(container, Gtk.Box):
                # If this is a vertical unit: first child is titlebar, second is scroller
                first = container.get_first_child()
                if isinstance(first, Gtk.Box) and 'term-titlebar' in first.get_css_classes():
                    if visible:
                        first.show()
                    else:
                        first.hide()
                # Recurse into children
                child = container.get_first_child()
                while child is not None:
                    process_container(child)
                    child = child.get_next_sibling()
            elif isinstance(container, Gtk.Paned):
                if container.get_start_child() is not None:
                    process_container(container.get_start_child())
                if container.get_end_child() is not None:
                    process_container(container.get_end_child())
            elif isinstance(container, Gtk.Notebook):
                for i in range(container.get_n_pages()):
                    page = container.get_nth_page(i)
                    process_container(page)

        root_child = self.get_child()
        if root_child is not None:
            process_container(root_child)

    def refresh_window_hints(self, always_on_top: bool, hide_from_taskbar: bool):
        try:
            if hasattr(self, 'set_keep_above'):
                self.set_keep_above(bool(always_on_top))
        except Exception:
            pass

    def refresh_titlebar_style(self):
        # Build CSS for titlebar colors/fonts from profile settings
        try:
            from .config import Config
            cfg = Config()
            prof = cfg.get_profile_by_name(cfg.get_profile())
        except Exception:
            prof = {}
        def sanitize(hexstr, fallback):
            try:
                s = str(hexstr or '').strip()
                if s:
                    return s
            except Exception:
                pass
            return fallback
        tx_fg = sanitize(prof.get('title_transmit_fg_color'), '#ffffff')
        tx_bg = sanitize(prof.get('title_transmit_bg_color'), '#c80003')
        rx_fg = sanitize(prof.get('title_receive_fg_color'), '#ffffff')
        rx_bg = sanitize(prof.get('title_receive_bg_color'), '#0076c9')
        in_fg = sanitize(prof.get('title_inactive_fg_color'), '#000000')
        in_bg = sanitize(prof.get('title_inactive_bg_color'), '#c0bebf')
        use_sys_font = bool(prof.get('title_use_system_font', True))
        font_str = sanitize(prof.get('title_font'), 'Sans 9')
        css_parts = []
        css_parts.append(f".term-titlebar.tx {{ background-color: {tx_bg}; color: {tx_fg}; }}")
        css_parts.append(f".term-titlebar.rx {{ background-color: {rx_bg}; color: {rx_fg}; }}")
        css_parts.append(f".term-titlebar.inactive {{ background-color: {in_bg}; color: {in_fg}; }}")
        if not use_sys_font and font_str:
            # Apply font to the titlebar area; labels inherit
            css_parts.append(f".term-titlebar {{ font: {font_str}; }}")
        try:
            data = ('\n'.join(css_parts)).encode('utf-8')
            self._title_css_provider.load_from_data(data)
        except Exception:
            pass
        try:
            if hasattr(self, 'set_skip_taskbar_hint'):
                self.set_skip_taskbar_hint(bool(hide_from_taskbar))
        except Exception:
            pass

    def refresh_titlebar_position(self, bottom: bool):
        # Move titlebars to top/bottom within each unit
        def process_container(container):
            if isinstance(container, Gtk.Box):
                first = container.get_first_child()
                # Identify unit by first child class
                if isinstance(first, Gtk.Box) and 'term-titlebar' in first.get_css_classes():
                    # Children expected: titlebar and scroller
                    titlebar = first
                    scroller = first.get_next_sibling()
                    if bottom:
                        # Want order: scroller, then titlebar
                        # If titlebar is first, reorder
                        try:
                            container.remove(titlebar)
                            if scroller is not None:
                                container.remove(scroller)
                                container.append(scroller)
                            container.append(titlebar)
                        except Exception:
                            pass
                    else:
                        # Want order: titlebar, then scroller
                        # If titlebar is not first, move it
                        try:
                            # Re-evaluate children
                            child0 = container.get_first_child()
                            if child0 is not titlebar:
                                # Remove both and re-add
                                # Find actual titlebar and scroller
                                # Iterate to find the titlebar again
                                tbar = None
                                scr = None
                                c = container.get_first_child()
                                while c is not None:
                                    if isinstance(c, Gtk.Box) and 'term-titlebar' in c.get_css_classes():
                                        tbar = c
                                    else:
                                        scr = c
                                    c = c.get_next_sibling()
                                if tbar is not None and scr is not None:
                                    container.remove(tbar)
                                    container.remove(scr)
                                    container.append(tbar)
                                    container.append(scr)
                        except Exception:
                            pass
                # Recurse
                child = container.get_first_child()
                while child is not None:
                    process_container(child)
                    child = child.get_next_sibling()
            elif isinstance(container, Gtk.Paned):
                if container.get_start_child() is not None:
                    process_container(container.get_start_child())
                if container.get_end_child() is not None:
                    process_container(container.get_end_child())
            elif isinstance(container, Gtk.Notebook):
                for i in range(container.get_n_pages()):
                    page = container.get_nth_page(i)
                    process_container(page)
        root = self.get_child()
        if root is not None:
            process_container(root)

    def _on_tab_next(self, *args):
        child = self.get_child()
        if isinstance(child, Gtk.Notebook) and child.get_n_pages() > 0:
            i = child.get_current_page()
            new_i = (i + 1) % child.get_n_pages()
            child.set_current_page(new_i)
            self._focus_terminal_in_page(child, new_i)
        return True

    def _on_tab_prev(self, *args):
        child = self.get_child()
        if isinstance(child, Gtk.Notebook) and child.get_n_pages() > 0:
            i = child.get_current_page()
            new_i = (i - 1) % child.get_n_pages()
            child.set_current_page(new_i)
            self._focus_terminal_in_page(child, new_i)
        return True

    def _on_new_tab(self, *args):
        self.open_new_tab()
        return True

    def _get_focused_terminal(self):
        # Walk up from focus widget to find a Gtk4Terminal
        focus = self.get_focus()
        from .gtk4terminal import Gtk4Terminal
        w = focus
        while w is not None and not isinstance(w, Gtk4Terminal):
            w = w.get_parent()
        return w

    def _on_split(self, orientation):
        term = self._get_focused_terminal()
        if term is not None:
            self.split_terminal(term, orientation)
        return True

    def _on_focus_direction(self, direction: str):
        term = self._get_focused_terminal()
        if term is None:
            return True
        scroller = term.get_parent()
        unit = scroller.get_parent()
        # Choose orientation and which sibling to focus based on direction
        if direction in ('left', 'right'):
            orientation = Gtk.Orientation.HORIZONTAL
        else:
            orientation = Gtk.Orientation.VERTICAL
        paned, child_is_start = self._find_parent_paned(unit, orientation)
        if paned is None:
            return True
        target = None
        if orientation == Gtk.Orientation.HORIZONTAL:
            if direction == 'left':
                target = paned.get_start_child()
            else:
                target = paned.get_end_child()
        else:
            if direction == 'up':
                target = paned.get_start_child()
            else:
                target = paned.get_end_child()
        # Avoid focusing the same unit
        if target is unit:
            target = None
        if target is None:
            return True
        # Find a terminal inside target and focus it
        t = self._find_terminal_in_container(target)
        if t is not None:
            t.grab_focus()
        return True

    def _on_split_auto(self, *args):
        term = self._get_focused_terminal()
        if term is None:
            return True
        # Choose orientation based on current allocation: wider -> left/right (HORIZONTAL), taller -> top/bottom (VERTICAL)
        w = term.get_allocated_width()
        h = term.get_allocated_height()
        orientation = Gtk.Orientation.HORIZONTAL if w >= h else Gtk.Orientation.VERTICAL
        self.split_terminal(term, orientation)
        return True

    def _on_close_window(self, *args):
        self.close()
        return True

    def _on_close_request(self, *args):
        # Respect ask_before_closing preference
        if getattr(self, '_force_close', False):
            return False
        from .config import Config
        cfg = Config()
        try:
            mode = cfg['ask_before_closing']
        except Exception:
            mode = 'multiple_terminals'
        # Count terminals
        root = self.get_child()
        count = len(list(self._iter_units_in_container(root))) if root is not None else 0
        need_confirm = False
        if mode == 'always':
            need_confirm = True
        elif mode == 'multiple_terminals' and count > 1:
            need_confirm = True
        if not need_confirm:
            return False
        # Show confirmation dialog
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.NONE,
                                text=_('Close window?'))
        dlg.format_secondary_text(_('There are multiple terminals open. Do you really want to close the window?'))
        dlg.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)
        dlg.add_button(_('Close'), Gtk.ResponseType.OK)
        def on_resp(d, resp):
            d.destroy()
            if resp == Gtk.ResponseType.OK:
                self._force_close = True
                try:
                    self.close()
                finally:
                    self._force_close = False
        dlg.connect('response', on_resp)
        dlg.present()
        return True

    def _on_close_term(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            # Attempt to terminate the shell in this terminal
            try:
                term.feed_child("exit\n")
            except Exception:
                # Fallback: collapse pane or close window
                self.on_child_exited(term, 0)
        return True

    def _on_copy(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            try:
                term.copy_clipboard()
            except Exception:
                pass
            # Clear selection after copy if configured
            try:
                from .config import Config
                if bool(Config()['clear_select_on_copy']) and hasattr(term, 'unselect_all'):
                    term.unselect_all()
            except Exception:
                pass
        return True

    def _on_copy_html(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'copy_selection_as_html'):
            try:
                term.copy_selection_as_html()
            except Exception:
                pass
        return True

    def _on_paste(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            try:
                term.paste_clipboard()
            except Exception:
                pass
        return True

    def _on_paste_selection(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'paste_primary'):  # Vte provides paste_primary
            try:
                term.paste_primary()
            except Exception:
                pass
        return True

    def _on_search(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, '_show_search_popover'):
            term._show_search_popover()
        return True

    def _on_toggle_scrollbar(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            scroller = term.get_parent()
            if isinstance(scroller, Gtk.ScrolledWindow):
                # Toggle between automatic and never
                hp, vp = scroller.get_policy()
                new_policy = Gtk.PolicyType.NEVER if hp != Gtk.PolicyType.NEVER else Gtk.PolicyType.AUTOMATIC
                scroller.set_policy(new_policy, Gtk.PolicyType.AUTOMATIC)
        return True

    def _on_full_screen(self, *args):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()
        return True

    def _on_reset_terminal(self, *args):
        term = self._get_focused_terminal()
        if term is None:
            return True
        try:
            term.reset(False)
        except TypeError:
            try:
                term.reset(False, False)
            except Exception:
                pass
        return True

    def _on_reset_clear_terminal(self, *args):
        term = self._get_focused_terminal()
        if term is None:
            return True
        try:
            term.reset(True)
        except TypeError:
            try:
                term.reset(True, True)
            except Exception:
                pass
        return True

    def _on_scroll_page(self, delta_pages):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'scroll_by_page'):
            term.scroll_by_page(delta_pages)
        return True

    def _on_scroll_line(self, delta_lines):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'scroll_by_line'):
            term.scroll_by_line(delta_lines)
        return True

    def _on_preferences(self, *args):
        from .preferences_gtk4 import PreferencesWindow
        dlg = PreferencesWindow(parent=self)
        dlg.present()
        return True

    def _on_edit_window_title(self, *args):
        # Reuse the terminal action by invoking its handler if possible
        term = self._get_focused_terminal()
        if term is not None:
            act = term._action_group.lookup_action("edit_window_title") if hasattr(term, "_action_group") else None
            if act:
                act.activate(None)
                return True
        # Fallback: simple dialog
        dialog = Gtk.Dialog(title="Set Window Title", transient_for=self, modal=True)
        box = dialog.get_content_area()
        entry = Gtk.Entry()
        entry.set_hexpand(True)
        box.append(entry)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show()
        def on_response(dlg, resp):
            if resp == Gtk.ResponseType.OK:
                txt = entry.get_text()
                if txt:
                    self.set_title(txt)
            dlg.destroy()
        dialog.connect("response", on_response)
        dialog.present()
        return True

    def _on_edit_tab_title(self, *args):
        child = self.get_child()
        if not isinstance(child, Gtk.Notebook):
            # No tabs yet; nothing to rename
            return True
        idx = child.get_current_page()
        if idx < 0:
            return True
        page = child.get_nth_page(idx)
        label = child.get_tab_label(page)
        # If the label is a plain Gtk.Label, wrap it once so we can attach gestures.
        if isinstance(label, Gtk.Label):
            new_widget = self._make_tab_label_widget(label.get_label() or str(idx+1), page)
            child.set_tab_label(page, new_widget)
            label = new_widget
        # Show popover anchored to the tab label
        self._show_tab_rename_popover(label, page)
        return True

    def _make_tab_label_widget(self, text: str, page_widget: Gtk.Widget) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        # Add a CSS class for GTK4 theming
        try:
            box.add_css_class('tab-label')
        except Exception:
            pass
        lbl = Gtk.Label(label=text)
        box.append(lbl)
        # Optional close button on tab
        try:
            from .config import Config
            if Config()['close_button_on_tab']:
                btn = Gtk.Button()
                btn.set_icon_name('window-close-symbolic')
                btn.add_css_class('flat')
                btn.set_has_frame(False)
                btn.connect('clicked', lambda b: self._close_tab_for_page(page_widget))
                box.append(btn)
        except Exception:
            pass
        # Click gestures: double-click left to rename; middle-click to close
        click = Gtk.GestureClick.new()
        def on_pressed(gesture, n_press, x, y):
            btn = gesture.get_current_button()
            if btn == 1 and n_press == 2:
                self._show_tab_rename_popover(box, page_widget)
            elif btn == 2 and n_press == 1:
                self._close_tab_for_page(page_widget)
        click.connect('pressed', on_pressed)
        box.add_controller(click)
        return box

    def _show_tab_rename_popover(self, tab_label_widget: Gtk.Widget, page_widget: Gtk.Widget):
        pop = Gtk.Popover()
        pop.set_parent(tab_label_widget)
        pop.set_has_arrow(True)
        pop.set_autohide(True)
        # Point popover to the full tab label area
        from gi.repository import Gdk
        rect = Gdk.Rectangle()
        rect.x = 0
        rect.y = 0
        rect.width = max(1, tab_label_widget.get_allocated_width())
        rect.height = max(1, tab_label_widget.get_allocated_height())
        try:
            pop.set_pointing_to(rect)
        except Exception:
            pass

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        entry = Gtk.Entry()
        # Pre-fill with current title if label child exists
        if isinstance(tab_label_widget, Gtk.Box):
            c = tab_label_widget.get_first_child()
            if isinstance(c, Gtk.Label) and c.get_label():
                entry.set_text(c.get_label())
        content.append(entry)
        ok_btn = Gtk.Button(label="OK")
        content.append(ok_btn)
        pop.set_child(content)

        def commit():
            txt = entry.get_text().strip()
            if isinstance(tab_label_widget, Gtk.Box):
                c = tab_label_widget.get_first_child()
                if isinstance(c, Gtk.Label):
                    c.set_label(txt or c.get_label())
            pop.popdown()

        key = Gtk.EventControllerKey()
        from gi.repository import Gdk
        def on_key(_ctrl, keyval, keycode, state):
            if keyval in (Gdk.KEY_Return, getattr(Gdk, 'KEY_KP_Enter', 0)):
                commit()
                return True
            if keyval == Gdk.KEY_Escape:
                pop.popdown()
                return True
            return False
        key.connect('key-pressed', on_key)
        entry.add_controller(key)
        # Also commit on entry.activate for reliability
        try:
            entry.connect('activate', lambda *_a: commit())
        except Exception:
            pass
        ok_btn.connect('clicked', lambda b: commit())
        pop.popup()
        entry.grab_focus()

    def _close_tab_for_page(self, page_widget: Gtk.Widget):
        nb, idx = self._find_notebook_page_for_widget(page_widget)
        if nb is None or idx < 0:
            return
        nb.remove_page(idx)
        n = nb.get_n_pages()
        if n > 0:
            nb.set_current_page(min(idx, n - 1))

    def split_terminal(self, term: Gtk4Terminal, orientation: Gtk.Orientation):
        scroller = term.get_parent()
        unit = scroller.get_parent()
        parent = unit.get_parent()
        # Build a new unit container for the new terminal (titlebar + scroller)
        new_term2, new_unit = self._new_terminal_container()
        # Apply profile/group behavior per config/profile
        try:
            from .config import Config
            cfg = Config()
            # Always split with current profile
            if bool(cfg['always_split_with_profile']):
                try:
                    prof = term.get_profile() if hasattr(term, 'get_profile') else None
                    if prof:
                        new_term2.set_profile(None, profile=prof)
                except Exception:
                    pass
            # Split to group if profile requests
            try:
                p = term.config.get_profile_by_name(term.config.get_profile()) if hasattr(term, 'config') else {}
                if p and bool(p.get('split_to_group', False)):
                    grp = getattr(term, '_group', None)
                    if grp:
                        self._set_unit_group(new_unit, grp)
            except Exception:
                pass
        except Exception:
            pass
        paned = Gtk.Paned(orientation=orientation)

        # For Gtk.Box, remember insertion position before removing
        insert_after = None
        if isinstance(parent, Gtk.Box):
            child = parent.get_first_child()
            prev = None
            while child is not None and child is not unit:
                prev = child
                child = child.get_next_sibling()
            insert_after = prev

        # Detach scroller from its current parent before reparenting
        if isinstance(parent, Gtk.Paned):
            if parent.get_start_child() is scroller:
                parent.set_start_child(None)
            else:
                parent.set_end_child(None)
        elif isinstance(parent, Gtk.Box):
            parent.remove(unit)
        elif isinstance(parent, Gtk.Notebook):
            # Replace in the current notebook page
            idx = -1
            for i in range(parent.get_n_pages()):
                if parent.get_nth_page(i) is unit:
                    idx = i
                    break
            if idx >= 0:
                parent.remove_page(idx)

        paned.set_start_child(unit)
        paned.set_end_child(new_unit)
        paned.set_resize_start_child(True)
        paned.set_resize_end_child(True)

        if isinstance(parent, Gtk.Paned):
            # Replace in same slot
            # Note: at this point, parent's child slot is empty
            if parent.get_start_child() is None:
                parent.set_start_child(paned)
            elif parent.get_end_child() is None:
                parent.set_end_child(paned)
            else:
                # Fallback: set end child
                parent.set_end_child(paned)
        elif isinstance(parent, Gtk.Box):
            if insert_after is None:
                parent.prepend(paned)
            else:
                parent.insert_child_after(paned, insert_after)
        elif isinstance(parent, Gtk.Notebook):
            # Insert into the same page index (or at end if unknown)
            page_label = Gtk.Label(label=str((idx if idx >= 0 else parent.get_n_pages()) + 1))
            if idx >= 0:
                parent.insert_page(paned, page_label, idx)
                parent.set_current_page(idx)
            else:
                parent.append_page(paned, page_label)
        else:
            self.set_child(paned)

        new_term2.grab_focus()

    def _on_switch_to_tab(self, index: int):
        child = self.get_child()
        if isinstance(child, Gtk.Notebook):
            if 0 <= index < child.get_n_pages():
                child.set_current_page(index)
                self._focus_terminal_in_page(child, index)
        return True

    def _on_layout_launcher(self, *args):
        try:
            from .layoutlauncher import LayoutLauncher
            LayoutLauncher()
        except Exception:
            pass
        return True

    def _on_create_group(self):
        term = self._get_focused_terminal()
        if term is None:
            return True
        # Reuse terminal popover to set group
        if hasattr(term, '_show_group_popover'):
            term._show_group_popover()
        return True

    def _on_group_all_toggle(self):
        # If any unit has a group, ungroup all; otherwise group all
        root = self.get_child()
        any_group = False
        for unit in self._iter_units_in_container(root):
            t = self._find_terminal_in_container(unit)
            if getattr(t, '_group', None):
                any_group = True
                break
        if any_group:
            self._ungroup_all_window()
        else:
            self._group_all_window()
        return True

    def _on_group_tab_toggle(self):
        # Similar logic per current tab
        nb = self.get_child() if isinstance(self.get_child(), Gtk.Notebook) else None
        if nb is None:
            return True
        idx = nb.get_current_page()
        if idx < 0:
            return True
        page = nb.get_nth_page(idx)
        any_group = False
        for unit in self._iter_units_in_container(page):
            t = self._find_terminal_in_container(unit)
            if getattr(t, '_group', None):
                any_group = True
                break
        if any_group:
            self._ungroup_all_tab()
        else:
            self._group_all_tab()
        return True

    # Resizing splits (adjust nearest Gtk.Paned position)
    def _on_resize_direction(self, direction: str):
        term = self._get_focused_terminal()
        if term is None:
            return True
        scroller = term.get_parent()
        if scroller is None:
            return True

        # Determine target orientation from direction
        if direction in ('left', 'right'):
            orientation = Gtk.Orientation.HORIZONTAL
        else:
            orientation = Gtk.Orientation.VERTICAL

        paned, child_is_start = self._find_parent_paned(scroller, orientation)
        if paned is None:
            return True

        amount = 30  # pixels per step
        pos = paned.get_position()
        # Sign logic: move handle so focused pane grows towards the direction
        delta = 0
        if orientation == Gtk.Orientation.HORIZONTAL:
            if child_is_start:
                delta = +amount if direction == 'right' else -amount
            else:
                delta = -amount if direction == 'right' else +amount
        else:  # VERTICAL
            if child_is_start:
                delta = +amount if direction == 'down' else -amount
            else:
                delta = -amount if direction == 'down' else +amount

        new_pos = max(0, pos + delta)
        # Clamp to paned allocation size
        alloc_w = paned.get_allocated_width()
        alloc_h = paned.get_allocated_height()
        limit = alloc_w if orientation == Gtk.Orientation.HORIZONTAL else alloc_h
        if limit > 0:
            new_pos = min(new_pos, limit)
        paned.set_position(new_pos)
        return True

    def _find_parent_paned(self, widget, orientation: Gtk.Orientation):
        """Return (paned, child_is_start) for the nearest Gtk.Paned ancestor
        matching orientation, or (None, False) if not found."""
        w = widget
        while w is not None:
            parent = w.get_parent()
            if isinstance(parent, Gtk.Paned) and parent.get_orientation() == orientation:
                # Determine whether widget is start or end child
                child_is_start = parent.get_start_child() is w
                return parent, child_is_start
            w = parent
        return None, False

    def _find_terminal_in_container(self, container: Gtk.Widget):
        from .gtk4terminal import Gtk4Terminal
        if isinstance(container, Gtk4Terminal):
            return container
        if isinstance(container, Gtk.Box):
            child = container.get_first_child()
            while child is not None:
                t = self._find_terminal_in_container(child)
                if t is not None:
                    return t
                child = child.get_next_sibling()
        elif isinstance(container, Gtk.Paned):
            for ch in (container.get_start_child(), container.get_end_child()):
                if ch is not None:
                    t = self._find_terminal_in_container(ch)
                    if t is not None:
                        return t
        return None

    def _count_terminals_in(self, container: Gtk.Widget) -> int:
        from .gtk4terminal import Gtk4Terminal
        count = 0
        if isinstance(container, Gtk4Terminal):
            return 1
        if isinstance(container, Gtk.Box):
            child = container.get_first_child()
            while child is not None:
                count += self._count_terminals_in(child)
                child = child.get_next_sibling()
        elif isinstance(container, Gtk.Paned):
            for ch in (container.get_start_child(), container.get_end_child()):
                if ch is not None:
                    count += self._count_terminals_in(ch)
        elif isinstance(container, Gtk.Notebook):
            for i in range(container.get_n_pages()):
                page = container.get_nth_page(i)
                count += self._count_terminals_in(page)
        return count

    def _title_for_container(self, container: Gtk.Widget) -> str | None:
        # Derive a title from the terminal inside the given container
        try:
            t = self._find_terminal_in_container(container)
            if t is not None and hasattr(t, 'get_window_title'):
                title = t.get_window_title()
                if title:
                    return title
        except Exception:
            pass
        return None

    def _on_cycle_focus(self, step: int):
        # Build a list of unit containers in current context (current tab if notebook; else whole window)
        root = self.get_child()
        context = None
        if isinstance(root, Gtk.Notebook):
            idx = root.get_current_page()
            if idx >= 0:
                context = root.get_nth_page(idx)
        else:
            context = root
        if context is None:
            return True
        units = list(self._iter_units_in_container(context))
        if not units:
            return True
        # Find index of current unit
        cur_term = self._get_focused_terminal()
        if cur_term is None:
            return True
        cur_unit = cur_term.get_parent().get_parent()
        try:
            cur_idx = units.index(cur_unit)
        except ValueError:
            cur_idx = 0
        new_idx = (cur_idx + step) % len(units)
        t = self._find_terminal_in_container(units[new_idx])
        if t is not None:
            t.grab_focus()
        return True

    def _on_help(self, *args):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                buttons=Gtk.ButtonsType.OK, text='Terminator GTK4 Port')
        dlg.format_secondary_text('Help will be ported. See port.md and README for status.')
        dlg.connect('response', lambda d, r: d.destroy())
        dlg.present()
        return True

    # Zoom callbacks operate on focused terminal
    def _on_zoom_in(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'zoom_step'):
            term.zoom_step(0.1)
        return True

    def _on_zoom_out(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'zoom_step'):
            term.zoom_step(-0.1)
        return True

    def _on_zoom_normal(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'zoom_reset'):
            term.zoom_reset()
        return True

    def _on_toggle_zoom(self, *args):
        term = self._get_focused_terminal()
        if term is None:
            return True
        unit = term.get_parent().get_parent()
        if getattr(self, '_zoomed_unit', None) is None:
            self._apply_zoom(unit)
        else:
            self._clear_zoom()
        return True

    def _apply_zoom(self, unit):
        # Hide all other units; remember zoomed unit
        self._zoomed_unit = unit
        def process(container):
            if isinstance(container, Gtk.Box):
                # If it's a unit, compare and hide others
                first = container.get_first_child()
                if isinstance(first, Gtk.Box) and 'term-titlebar' in first.get_css_classes():
                    if container is not unit:
                        container.hide()
                    else:
                        container.show()
                child = container.get_first_child()
                while child is not None:
                    process(child)
                    child = child.get_next_sibling()
            elif isinstance(container, Gtk.Paned):
                if container.get_start_child():
                    process(container.get_start_child())
                if container.get_end_child():
                    process(container.get_end_child())
            elif isinstance(container, Gtk.Notebook):
                for i in range(container.get_n_pages()):
                    page = container.get_nth_page(i)
                    process(page)
        root_child = self.get_child()
        if root_child is not None:
            process(root_child)

    def _clear_zoom(self):
        self._zoomed_unit = None
        # Show all units again
        def process(container):
            if isinstance(container, Gtk.Box):
                first = container.get_first_child()
                if isinstance(first, Gtk.Box) and 'term-titlebar' in first.get_css_classes():
                    container.show()
                child = container.get_first_child()
                while child is not None:
                    process(child)
                    child = child.get_next_sibling()
            elif isinstance(container, Gtk.Paned):
                if container.get_start_child():
                    process(container.get_start_child())
                if container.get_end_child():
                    process(container.get_end_child())
            elif isinstance(container, Gtk.Notebook):
                for i in range(container.get_n_pages()):
                    page = container.get_nth_page(i)
                    process(page)
        root_child = self.get_child()
        if root_child is not None:
            process(root_child)

    def zoom_terminal(self, term: Gtk4Terminal):
        # Zoom the unit containing this terminal
        unit = term.get_parent().get_parent()
        if getattr(self, '_zoomed_unit', None) is None or self._zoomed_unit is not unit:
            self._apply_zoom(unit)
        else:
            self._clear_zoom()

    def _on_full_screen(self, *args):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()
        return True

    def _on_hide_window(self, *args):
        try:
            self.hide()
        except Exception:
            pass
        return True

    def _on_new_window(self, *args):
        app = self.get_application()
        try:
            win = TerminatorGtk4Window(application=app)
            win.present()
        except Exception:
            pass

    # Zoom callbacks operate on focused terminal
    def _on_zoom_in(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'zoom_step'):
            term.zoom_step(0.1)
        return True

    def _on_zoom_out(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'zoom_step'):
            term.zoom_step(-0.1)
        return True

    def _on_zoom_normal(self, *args):
        term = self._get_focused_terminal()
        if term is not None and hasattr(term, 'zoom_reset'):
            term.zoom_reset()
        return True

    def zoom_terminal(self, term: Gtk4Terminal):
        # TODO: implement zoom toggle using a revealer or overlay
        pass

    def open_new_tab(self):
        child = self.get_child()
        notebook = None
        if isinstance(child, Gtk.Notebook):
            notebook = child
        else:
            # Convert current content into a notebook
            notebook = Gtk.Notebook()
            notebook.set_hexpand(True)
            notebook.set_vexpand(True)
            try:
                if hasattr(notebook, 'set_group_name'):
                    notebook.set_group_name('terminator-tabs')
            except Exception:
                pass
            self._install_notebook_behaviors(notebook)
            self._apply_notebook_prefs(notebook)
            # Move existing child into first tab
            if isinstance(child, Gtk.Box):
                # Assume first child is the scroller/paned
                existing = child.get_first_child()
                if existing is not None:
                    child.remove(existing)
                self.set_child(notebook)
                if existing is not None:
                    title = self._title_for_container(existing) or "1"
                    notebook.append_page(existing, self._make_tab_label_widget(title, existing))
            else:
                existing = child
                # Detach current child
                self.set_child(None)
                # Set notebook as the new child and append existing
                self.set_child(notebook)
                if existing is not None:
                    title = self._title_for_container(existing) or "1"
                    notebook.append_page(existing, self._make_tab_label_widget(title, existing))

        # Add new page (respect new_tab_after_current_tab)
        term, unit = self._new_terminal_container()
        # Title from terminal if available, else fallback to numeric
        try:
            new_title = term.get_window_title() if hasattr(term, 'get_window_title') else None
        except Exception:
            new_title = None
        if not new_title:
            new_title = str(notebook.get_n_pages()+1)
        tab_lbl = self._make_tab_label_widget(new_title, unit)
        from .config import Config
        insert_after_current = False
        try:
            insert_after_current = bool(Config()['new_tab_after_current_tab'])
        except Exception:
            insert_after_current = False
        if insert_after_current and notebook.get_n_pages() > 0:
            cur = notebook.get_current_page()
            page_num = notebook.insert_page(unit, tab_lbl, cur + 1)
        else:
            page_num = notebook.append_page(unit, tab_lbl)
        notebook.set_current_page(page_num)
        # Make tab reorderable per preference
        try:
            from .config import Config
            if hasattr(notebook, 'set_tab_reorderable') and bool(Config()['detachable_tabs']):
                notebook.set_tab_reorderable(unit, True)
        except Exception:
            pass
        # Ensure focus returns to the new terminal, not the tab header
        try:
            term.grab_focus()
        except Exception:
            pass
        # Update active tab CSS classes
        try:
            self._refresh_tab_label_active_classes(notebook, notebook.get_current_page())
        except Exception:
            pass

    def _install_notebook_behaviors(self, notebook: Gtk.Notebook):
        # Scroll wheel over the tab bar switches pages
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        def on_scroll(controller, dx, dy):
            n = notebook.get_n_pages()
            if n <= 0:
                return False
            cur = notebook.get_current_page()
            if dy < 0:
                new_i = (cur + 1) % n
                notebook.set_current_page(new_i)
                self._focus_terminal_in_page(notebook, new_i)
            elif dy > 0:
                new_i = (cur - 1 + n) % n
                notebook.set_current_page(new_i)
                self._focus_terminal_in_page(notebook, new_i)
            return True
        scroll.connect('scroll', on_scroll)
        notebook.add_controller(scroll)
        # Focus terminal when tab is switched by any means
        def on_switched(nb, page, page_num):
            self._focus_terminal_in_page(nb, page_num)
            try:
                self._refresh_tab_label_active_classes(nb, page_num)
            except Exception:
                pass
        try:
            notebook.connect('switch-page', on_switched)
        except Exception:
            pass
        # Support detachable tabs via create-window if enabled in Config
        try:
            def on_create_window(nb, widget, x, y):
                # Only detach if preference allows it
                try:
                    from .config import Config
                    if not bool(Config()['detachable_tabs']):
                        return None
                except Exception:
                    pass
                app = self.get_application()
                new_win = TerminatorGtk4Window(application=app)
                # Prepare a notebook in the new window
                new_nb = Gtk.Notebook()
                new_nb.set_hexpand(True)
                new_nb.set_vexpand(True)
                try:
                    if hasattr(new_nb, 'set_group_name'):
                        new_nb.set_group_name('terminator-tabs')
                except Exception:
                    pass
                new_win.set_child(new_nb)
                new_win._install_notebook_behaviors(new_nb)
                new_win._apply_notebook_prefs(new_nb)
                # Label text from source label if possible
                try:
                    src_lbl = nb.get_tab_label(widget)
                    if isinstance(src_lbl, Gtk.Box):
                        c = src_lbl.get_first_child()
                        text = c.get_label() if isinstance(c, Gtk.Label) else "1"
                    elif isinstance(src_lbl, Gtk.Label):
                        text = src_lbl.get_label() or "1"
                    else:
                        text = "1"
                except Exception:
                    text = "1"
                new_nb.append_page(widget, new_win._make_tab_label_widget(text, widget))
                new_win.present()
                try:
                    new_win._refresh_tab_label_active_classes(new_nb, new_nb.get_current_page())
                except Exception:
                    pass
                return new_nb
            notebook.connect('create-window', on_create_window)
        except Exception:
            pass

    def _focus_terminal_in_page(self, notebook: Gtk.Notebook, idx: int):
        try:
            page = notebook.get_nth_page(idx)
            t = self._find_terminal_in_container(page)
            if t is not None:
                t.grab_focus()
        except Exception:
            pass

    def _refresh_tab_label_active_classes(self, notebook: Gtk.Notebook, active_index: int):
        try:
            n = notebook.get_n_pages()
            for i in range(n):
                page = notebook.get_nth_page(i)
                lbl = notebook.get_tab_label(page)
                if isinstance(lbl, Gtk.Box):
                    if i == active_index:
                        try:
                            lbl.add_css_class('active')
                        except Exception:
                            pass
                    else:
                        try:
                            if hasattr(lbl, 'remove_css_class'):
                                lbl.remove_css_class('active')
                        except Exception:
                            pass
        except Exception:
            pass

    def _apply_notebook_prefs(self, notebook: Gtk.Notebook):
        # Apply tabbar preferences from Config
        from .config import Config
        cfg = Config()
        try:
            # Scrollable tab bar
            if hasattr(notebook, 'set_scrollable'):
                notebook.set_scrollable(bool(cfg['scroll_tabbar']))
        except Exception:
            pass
        try:
            if hasattr(notebook, 'set_group_name'):
                notebook.set_group_name('terminator-tabs')
        except Exception:
            pass
        try:
            # Homogeneous tabs
            if hasattr(notebook, 'set_homogeneous_tabs'):
                notebook.set_homogeneous_tabs(bool(cfg['homogeneous_tabbar']))
        except Exception:
            pass
        try:
            # Tab position
            pos = (cfg['tab_position'] or 'top').lower()
            mapping = {
                'top': Gtk.PositionType.TOP if hasattr(Gtk, 'PositionType') else 0,
                'bottom': Gtk.PositionType.BOTTOM if hasattr(Gtk, 'PositionType') else 3,
                'left': Gtk.PositionType.LEFT if hasattr(Gtk, 'PositionType') else 1,
                'right': Gtk.PositionType.RIGHT if hasattr(Gtk, 'PositionType') else 2,
            }
            if hasattr(notebook, 'set_tab_pos') and pos in mapping:
                notebook.set_tab_pos(mapping[pos])
        except Exception:
            pass
        # Reorderable tabs within the notebook - use 'detachable_tabs'
        try:
            reorder = bool(cfg['detachable_tabs'])
            n = notebook.get_n_pages()
            for i in range(n):
                page = notebook.get_nth_page(i)
                if hasattr(notebook, 'set_tab_reorderable'):
                    notebook.set_tab_reorderable(page, reorder)
                if hasattr(notebook, 'set_tab_detachable'):
                    notebook.set_tab_detachable(page, reorder)
        except Exception:
            pass

    # --- Layout loading (GTK4) ---
    def open_layout_window_by_name(self, name: str):
        from .config import Config
        cfg = Config()
        try:
            layout = cfg.get_layout(name)
        except Exception:
            layout = None
        if not layout:
            return
        app = self.get_application()
        win = TerminatorGtk4Window(application=app)
        try:
            win._apply_layout(layout)
        except Exception:
            pass
        win.present()

    def _apply_layout(self, layout_root: dict):
        # Expect a 'children' with a single root child node
        if 'children' not in layout_root or not layout_root['children']:
            return
        # Apply window properties: title, maximised, fullscreen, size, position (best effort)
        try:
            title = layout_root.get('title')
            if title:
                self.set_title(title)
        except Exception:
            pass
        try:
            maximised = layout_root.get('maximised')
            if str(maximised) == 'True':
                self.maximize()
        except Exception:
            pass
        try:
            fullscreen = layout_root.get('fullscreen')
            if str(fullscreen) == 'True':
                self.fullscreen()
        except Exception:
            pass
        try:
            size = layout_root.get('size')
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                self.set_default_size(int(size[0]), int(size[1]))
            elif isinstance(size, str) and 'x' in size:
                w, h = size.split('x', 1)
                self.set_default_size(int(w), int(h))
        except Exception:
            pass
        try:
            pos = layout_root.get('position')
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                self.move(int(pos[0]), int(pos[1]))
            elif isinstance(pos, str) and ':' in pos:
                x, y = pos.split(':', 1)
                self.move(int(x), int(y))
        except Exception:
            pass
        # Remove current content
        self.set_child(None)
        # Build the child content
        self._uuid_unit_map = {}
        child_node = list(layout_root['children'].values())[0]
        widget = self._build_node(child_node)
        if isinstance(widget, Gtk.Notebook):
            self._install_notebook_behaviors(widget)
            self._apply_notebook_prefs(widget)
        self.set_child(widget)
        # Ensure tab active-state CSS classes are in sync
        try:
            if isinstance(widget, Gtk.Notebook):
                self._refresh_tab_label_active_classes(widget, widget.get_current_page())
        except Exception:
            pass
        # Restore last active terminal focus if available
        try:
            last_uuid = layout_root.get('last_active_term')
            if last_uuid:
                self._focus_terminal_by_uuid(last_uuid)
        except Exception:
            pass

    def _build_node(self, node: dict):
        t = (node.get('type') or '').lower()
        if t == 'terminal':
            term, unit = self._new_terminal_container()
            # Apply terminal properties
            try:
                prof = node.get('profile')
                if prof:
                    term.config.set_profile(prof, True)
                    term.apply_profile()
            except Exception:
                pass
            try:
                grp = node.get('group')
                if grp:
                    self._set_unit_group(unit, grp)
            except Exception:
                pass
            try:
                title = node.get('title')
                if title:
                    tb = unit.get_first_child()
                    if hasattr(tb, 'set_title'):
                        tb.set_title(title)
            except Exception:
                pass
            try:
                uuid = node.get('uuid')
                if uuid:
                    self._uuid_unit_map[str(uuid)] = unit
            except Exception:
                pass
            return unit
        elif t in ('vpaned', 'hpaned'):
            orientation = Gtk.Orientation.VERTICAL if t == 'vpaned' else Gtk.Orientation.HORIZONTAL
            paned = Gtk.Paned(orientation=orientation)
            children = list(node.get('children', {}).values())
            # Sort by 'order' if present
            try:
                children.sort(key=lambda c: c.get('order', 0))
            except Exception:
                pass
            if len(children) >= 1:
                paned.set_start_child(self._build_node(children[0]))
            if len(children) >= 2:
                paned.set_end_child(self._build_node(children[1]))
            # Apply ratio if present after realize
            try:
                ratio = float(node.get('ratio', 0.5))
                def set_pos_once(p):
                    alloc = p.get_allocation()
                    size = alloc.width if orientation == Gtk.Orientation.HORIZONTAL else alloc.height
                    if size > 0:
                        p.set_position(int(size * ratio))
                        return False
                    return True
                paned.connect('map', lambda w: GLib.idle_add(set_pos_once, paned))
            except Exception:
                pass
            return paned
        elif t == 'notebook':
            nb = Gtk.Notebook()
            self._install_notebook_behaviors(nb)
            self._apply_notebook_prefs(nb)
            # Build pages sorted by order
            children = list(node.get('children', {}).values())
            try:
                children.sort(key=lambda c: c.get('order', 0))
            except Exception:
                pass
            labels = node.get('labels') or []
            for i, ch in enumerate(children):
                page = self._build_node(ch)
                label_text = labels[i] if i < len(labels) else str(i+1)
                nb.append_page(page, self._make_tab_label_widget(label_text, page))
            # Active page
            try:
                ap = int(node.get('active_page', 0))
                if 0 <= ap < nb.get_n_pages():
                    nb.set_current_page(ap)
                    # Focus last active terminal on this page if provided
                    lat = node.get('last_active_term')
                    if isinstance(lat, (list, tuple)) and ap < len(lat) and lat[ap]:
                        self._focus_terminal_by_uuid(str(lat[ap]))
            except Exception:
                pass
            return nb
        else:
            # Unknown node type; fallback to a single terminal
            return self._new_terminal_container()[1]

    def _focus_terminal_by_uuid(self, uuid: str):
        unit = self._uuid_unit_map.get(str(uuid))
        if not unit:
            return
        # If contained in a notebook, switch to that page first
        nb, idx = self._find_notebook_page_for_widget(unit)
        if nb is not None and idx >= 0:
            nb.set_current_page(idx)
        t = self._find_terminal_in_container(unit)
        if t is not None:
            t.grab_focus()

    def refresh_notebook_prefs(self):
        # Apply notebook prefs to all notebooks in this window
        def visit(w):
            if isinstance(w, Gtk.Notebook):
                self._apply_notebook_prefs(w)
            if isinstance(w, Gtk.Box):
                c = w.get_first_child()
                while c is not None:
                    visit(c)
                    c = c.get_next_sibling()
            elif isinstance(w, Gtk.Paned):
                if w.get_start_child() is not None:
                    visit(w.get_start_child())
                if w.get_end_child() is not None:
                    visit(w.get_end_child())
        root = self.get_child()
        if root is not None:
            visit(root)

    def _on_move_tab(self, delta: int):
        nb = self.get_child() if isinstance(self.get_child(), Gtk.Notebook) else None
        if nb is None:
            return True
        n = nb.get_n_pages()
        if n <= 1:
            return True
        cur = nb.get_current_page()
        new = (cur + delta) % n
        if new == cur:
            return True
        page = nb.get_nth_page(cur)
        label = nb.get_tab_label(page)
        # Remove and reinsert at new index
        nb.remove_page(cur)
        nb.insert_page(page, label, new)
        nb.set_current_page(new)
        return True

    def refresh_tab_close_buttons(self):
        # Update existing tab label widgets to add or remove close buttons based on preference
        from .config import Config
        try:
            want = bool(Config()['close_button_on_tab'])
        except Exception:
            want = True

        def update_label_widget(label_widget: Gtk.Widget, page_widget: Gtk.Widget):
            if not isinstance(label_widget, Gtk.Box):
                return
            has_btn = False
            btn_widget = None
            child = label_widget.get_first_child()
            while child is not None:
                if isinstance(child, Gtk.Button):
                    btn_widget = child
                    has_btn = True
                    break
                child = child.get_next_sibling()
            if want and not has_btn:
                btn = Gtk.Button()
                btn.set_icon_name('window-close-symbolic')
                btn.add_css_class('flat')
                btn.set_has_frame(False)
                btn.connect('clicked', lambda b: self._close_tab_for_page(page_widget))
                label_widget.append(btn)
            elif not want and has_btn and btn_widget is not None:
                label_widget.remove(btn_widget)

        def visit(w):
            if isinstance(w, Gtk.Notebook):
                n = w.get_n_pages()
                for i in range(n):
                    page = w.get_nth_page(i)
                    lbl = w.get_tab_label(page)
                    update_label_widget(lbl, page)
            if isinstance(w, Gtk.Box):
                c = w.get_first_child()
                while c is not None:
                    visit(c)
                    c = c.get_next_sibling()
            elif isinstance(w, Gtk.Paned):
                if w.get_start_child() is not None:
                    visit(w.get_start_child())
                if w.get_end_child() is not None:
                    visit(w.get_end_child())
        root = self.get_child()
        if root is not None:
            visit(root)

    def _on_cycle_profile(self, step: int):
        # Cycle profile for focused terminal (per-terminal config)
        term = self._get_focused_terminal()
        if term is None or not hasattr(term, 'config'):
            return True
        cfg = term.config
        try:
            profiles = sorted(cfg.list_profiles(), key=str.lower)
        except Exception:
            profiles = []
        if not profiles:
            return True
        cur = None
        try:
            cur = cfg.get_profile()
        except Exception:
            cur = 'default'
        try:
            idx = profiles.index(cur)
        except ValueError:
            idx = 0
        new = profiles[(idx + step) % len(profiles)]
        try:
            cfg.set_profile(new, True)
            if hasattr(term, 'apply_profile'):
                term.apply_profile()
            # Update action state so menu reflects current selection
            ag = term._action_group.lookup_action('profile') if hasattr(term, '_action_group') else None
            if ag is not None:
                from gi.repository import GLib
                ag.set_state(GLib.Variant('s', new))
        except Exception:
            pass
        return True

    def _notify_bell_for_terminal(self, term):
        scroller = term.get_parent()
        unit = scroller.get_parent() if scroller is not None else None
        if unit is None:
            return
        # titlebar is first child
        tb = unit.get_first_child() if isinstance(unit, Gtk.Box) else None
        if tb is None:
            return
        # Show bell for 1s
        try:
            if hasattr(tb, 'show_bell'):
                tb.show_bell()
                GLib.timeout_add(1000, lambda: (tb.hide_bell(), False)[1])
        except Exception:
            pass
