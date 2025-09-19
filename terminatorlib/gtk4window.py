"""Minimal GTK4 Window hosting a single VTE terminal.

This is a stepping stone toward a full GTK4 port. It purposefully
implements only a small subset of behaviors so we can iterate.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk

from .gtk4terminal import Gtk4Terminal


class TerminatorGtk4Window(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("Terminator (GTK4 preview)")
        self.set_default_size(1000, 700)

        # Layout: simple box with one terminal for now
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        term = Gtk4Terminal()
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(term)

        # In Gtk4, append replaces pack_* and add
        root.append(scroller)

        # Spawn user's shell
        term.spawn_login_shell()

