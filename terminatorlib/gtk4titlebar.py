"""GTK4 Titlebar widget for a terminal unit.

Provides minimal controls:
- Title label with double-click to rename the tab anchored over the tab header.
- Group button that opens a small popover to set a group name (visual only).
- Bell icon placeholder (hidden by default).
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject
from .translation import _


class Gtk4Titlebar(Gtk.Box):
    __gtype_name__ = 'Gtk4Titlebar'

    __gsignals__ = {
        # Emitted when a group is created via the popover entry
        'create-group': (GObject.SignalFlags.RUN_LAST, None, (GObject.TYPE_STRING,)),
    }

    def __init__(self, window: Gtk.Window, unit_container: Gtk.Widget):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_css_class('term-titlebar')
        self._window = window
        self._unit = unit_container

        # Left: broadcast state icon + group button + group name (visual only)
        self._broadcast = Gtk.Image.new_from_icon_name('radio-button-off-symbolic')
        self._broadcast.add_css_class('dim-label')
        self.append(self._broadcast)

        self._group_btn = Gtk.Button()
        self._group_btn.set_icon_name('system-users-symbolic')
        self._group_btn.add_css_class('flat')
        self._group_btn.set_has_frame(False)
        self._group_btn.connect('clicked', self._on_group_clicked)
        self.append(self._group_btn)

        self._group_label = Gtk.Label(label='')
        self._group_label.add_css_class('dim-label')
        self.append(self._group_label)

        # Title label expands
        self._title = Gtk.Label(label='Terminal', xalign=0)
        self._title.set_hexpand(True)
        self.append(self._title)

        # Bell icon (hidden by default)
        self._bell = Gtk.Image.new_from_icon_name('dialog-warning-symbolic')
        self._bell.set_visible(False)
        self.append(self._bell)

        # Double-click anywhere on titlebar to rename the tab over the tab header
        click = Gtk.GestureClick.new()
        click.set_button(1)
        click.connect('pressed', self._on_pressed)
        self.add_controller(click)

        # Right-click popover with quick actions
        rclick = Gtk.GestureClick.new()
        rclick.set_button(3)
        def on_rclick(gesture, n_press, x, y):
            self._show_actions_popover(x, y)
        rclick.connect('pressed', on_rclick)
        self.add_controller(rclick)

    # External API
    def set_title(self, text: str):
        self._title.set_label(text)

    def show_bell(self):
        self._bell.set_visible(True)

    def hide_bell(self):
        self._bell.set_visible(False)

    def set_broadcast_state(self, mode: str, is_member: bool):
        """mode: 'off' | 'group' | 'all'"""
        icon = 'radio-button-off-symbolic'
        if mode == 'all':
            icon = 'view-grid-symbolic'
        elif mode == 'group':
            icon = 'system-users-symbolic' if is_member else 'radio-button-off-symbolic'
        try:
            self._broadcast.set_from_icon_name(icon)
        except Exception:
            pass

    def set_active_state(self, state: str):
        """state: 'tx' | 'rx' | 'inactive' -> toggles CSS classes"""
        for cls in ('tx', 'rx', 'inactive'):
            if cls in self.get_css_classes():
                self.remove_css_class(cls)
        if state in ('tx', 'rx', 'inactive'):
            self.add_css_class(state)

    # Internal callbacks
    def _on_pressed(self, gesture, n_press, x, y):
        if n_press == 2:
            # Request the window to rename the tab for our unit, anchored at the tab header
            if hasattr(self._window, '_rename_tab_for_unit'):
                self._window._rename_tab_for_unit(self._unit)

    def _on_group_clicked(self, button):
        pop = Gtk.Popover()
        pop.set_parent(button)
        pop.set_has_arrow(True)
        pop.set_autohide(True)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        entry = Gtk.Entry()
        entry.set_placeholder_text('Group name…')
        if self._group_label.get_label():
            entry.set_text(self._group_label.get_label())
        box.append(entry)
        ok = Gtk.Button(label='Set')
        box.append(ok)
        pop.set_child(box)

        def commit():
            name = entry.get_text().strip()
            self._group_label.set_label(name)
            self.emit('create-group', name)
            pop.popdown()

        ok.connect('clicked', lambda b: commit())
        pop.popup()
        entry.grab_focus()

    def _show_actions_popover(self, x=0, y=0):
        pop = Gtk.Popover()
        pop.set_parent(self)
        pop.set_has_arrow(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        def add_action(label, cb):
            btn = Gtk.Button(label=label)
            btn.connect('clicked', lambda b: (cb(), pop.popdown()))
            box.append(btn)

        win = self._window

        add_action(_('Rename Tab'), lambda: getattr(win, '_on_edit_tab_title')())
        add_action(_('Set Window Title'), lambda: getattr(win, '_on_edit_window_title')())
        # Splits
        try:
            from gi.repository import Gtk as _Gtk
            add_action(_('Split Horizontally'), lambda: getattr(win, '_on_split')(_Gtk.Orientation.HORIZONTAL))
            add_action(_('Split Vertically'), lambda: getattr(win, '_on_split')(_Gtk.Orientation.VERTICAL))
        except Exception:
            pass
        # Group
        add_action(_('Create Group…'), lambda: getattr(win, '_on_create_group')())
        # Close terminal
        add_action(_('Close Terminal'), lambda: getattr(win, '_on_close_term')())

        pop.set_child(box)
        pop.popup()
