"""Minimal GTK4 application bootstrap for Terminator.

This is an experimental entrypoint to begin the GTK 4 port. It opens
an ApplicationWindow with a single Vte terminal and basic spawn.
"""

import os
import shlex
import shutil
from typing import List, Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk, GLib, Gio

from .gtk4window import TerminatorGtk4Window


class TerminatorGtk4App(Gtk.Application):
    def __init__(self):
        # Gtk.Application inherits from Gio.Application; use Gio.ApplicationFlags
        super().__init__(application_id='io.github.gnome.Terminator.Gtk4', flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self, *args):  # type: ignore[override]
        # Create a single window with one terminal for now
        win = TerminatorGtk4Window(application=self)
        win.present()

    def run(self, argv: Optional[List[str]] = None) -> int:
        # Match Gtk.Application.run signature expecting a list of strings
        if argv is None:
            argv = []
        return super().run(argv)
