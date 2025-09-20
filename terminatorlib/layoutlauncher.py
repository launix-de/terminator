#!/usr/bin/env python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""layoutlauncher.py - GTK4/GTK3 hybrid Layout Launcher window

Uses GTK4 widgets when available. Falls back to the legacy
Glade/GTK3 UI to remain importable while other modules are ported.
"""

import os
from gi.repository import Gtk, Gio

from .util import dbg, spawn_new_terminator
from . import config
from .translation import _
from .terminator import Terminator


class LayoutLauncher:
    """GTK4 implementation of the Layout Launcher window"""

    def __init__(self):
        self.terminator = Terminator()
        self.terminator.register_launcher_window(self)

        self.config = config.Config()
        self.config.base.reload()

        if hasattr(Gtk, 'ListView') and hasattr(Gtk, 'StringList'):
            # GTK4 path
            self.window = Gtk.Window()
            self.window.set_title(_('Terminator Layout Launcher'))
            self.window.set_default_size(250, 300)
            self.window.connect('close-request', self.on_close_request)

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            root.set_margin_top(7)
            root.set_margin_bottom(7)
            root.set_margin_start(7)
            root.set_margin_end(7)
            self.window.set_child(root)

            # List of layouts in a ListView
            self.string_list = Gtk.StringList()
            self.selection = Gtk.SingleSelection(model=self.string_list)

            factory = Gtk.SignalListItemFactory()
            factory.connect('setup', self._on_factory_setup)
            factory.connect('bind', self._on_factory_bind)

            self.list_view = Gtk.ListView(model=self.selection, factory=factory)
            self.list_view.set_vexpand(True)
            self.list_view.connect('activate', self._on_list_activate)

            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.set_child(self.list_view)
            root.append(scroller)

            # Action row with Launch button
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            root.append(hbox)

            self.launch_button = Gtk.Button(label=_('Launch'))
            self.launch_button.connect('clicked', self.on_launch_clicked)
            hbox.append(Gtk.Box())  # spacer
            hbox.append(self.launch_button)

            self.update_layouts()
            self.window.present()
        else:
            # GTK3 fallback (legacy Glade-based UI)
            self.builder = Gtk.Builder()
            try:
                (head, _tail) = os.path.split(config.__file__)
                librarypath = os.path.join(head, 'layoutlauncher.glade')
                with open(librarypath, 'r') as gladefile:
                    gladedata = gladefile.read()
            except Exception as ex:
                print('Failed to find layoutlauncher.glade')
                print(ex)
                return

            self.builder.add_from_string(gladedata)
            self.window = self.builder.get_object('layoutlauncherwin')

            icon_theme = Gtk.IconTheme.get_default()
            if hasattr(icon_theme, 'lookup_icon') and icon_theme.lookup_icon('terminator-layout', 48, 0):
                self.window.set_icon_name('terminator-layout')
            else:
                dbg('Unable to load Terminator layout launcher icon')
                try:
                    icon = self.window.render_icon(Gtk.STOCK_DIALOG_INFO, Gtk.IconSize.BUTTON)
                    self.window.set_icon(icon)
                except Exception:
                    pass

            self.window.set_size_request(250, 300)
            self.builder.connect_signals(self)
            self.window.connect('destroy', self.on_destroy_event)
            self.window.show_all()
            self.layouttreeview = self.builder.get_object('layoutlist')
            self.layouttreestore = self.builder.get_object('layoutstore')
            self.update_layouts()

    # List item factory handlers
    def _on_factory_setup(self, _factory, list_item):
        label = Gtk.Label(xalign=0)
        list_item.set_child(label)

    def _on_factory_bind(self, _factory, list_item):
        item = list_item.get_item()
        if isinstance(item, Gio.ListModel):
            # Not used with Gtk.StringList
            return
        label = list_item.get_child()
        label.set_text(item.get_string())

    def update_layouts(self):
        """Refresh the layout list (default first, then alpha)."""
        # Rebuild the string list to avoid stale items
        self.string_list.splice(0, self.string_list.get_n_items(), [])
        layouts = list(self.config.list_layouts())
        layouts.sort(key=str.lower)
        # Move 'default' to the top if present
        if 'default' in layouts:
            layouts.remove('default')
            items = ['default'] + layouts
        else:
            items = layouts
        for name in items:
            self.string_list.append(name)

        # Select first item by default
        if self.string_list.get_n_items() > 0:
            self.selection.set_selected(0)

    def _on_list_activate(self, _list_view, position):
        self.launch_layout(position)

    def on_launch_clicked(self, _button):
        pos = self.selection.get_selected()
        self.launch_layout(pos)

    def launch_layout(self, position):
        if position < 0 or position >= self.string_list.get_n_items():
            return
        layout = self.string_list.get_string(position)
        dbg('Launching layout %s' % layout)
        spawn_new_terminator(self.terminator.origcwd, ['-u', '-l', layout])

    def on_close_request(self, _window):
        dbg('LayoutLauncher window close request')
        self.terminator.deregister_launcher_window(self)
        return False


if __name__ == '__main__':
    # Standalone launching is not supported in GTK4 without an Application.
    # This module is intended to be invoked from within Terminator.
    launcher = LayoutLauncher()
