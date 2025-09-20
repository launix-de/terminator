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
from .config import Config

from .gtk4window import TerminatorGtk4Window


class TerminatorGtk4App(Gtk.Application):
    def __init__(self):
        # Gtk.Application inherits from Gio.Application; use Gio.ApplicationFlags
        super().__init__(application_id='io.github.gnome.Terminator.Gtk4', flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self, *args):  # type: ignore[override]
        # Create a single window with one terminal for now
        win = TerminatorGtk4Window(application=self)

        # Apply legacy options via Config
        try:
            cfg = Config()
            opts = cfg.options_get()
        except Exception:
            opts = None

        if opts:
            # Geometry
            if opts.geometry:
                # rudimentary WxH+X+Y handling
                try:
                    size_pos = opts.geometry
                    size, _, pos = size_pos.partition('+')
                    if 'x' in size:
                        w, h = size.split('x', 1)
                        win.set_default_size(int(w), int(h))
                    # positions are handled by window managers; best effort:
                    if pos:
                        try:
                            x_str, _, y_str = pos.partition('+')
                            win.move(int(x_str), int(y_str))  # Gtk4: still supported via Window.move
                        except Exception:
                            pass
                except Exception:
                    pass

            if getattr(opts, 'maximise', False):
                win.maximize()
            if getattr(opts, 'fullscreen', False):
                win.fullscreen()

            # Command/working directory
            try:
                term = win.term
                from .gtk4terminal import Gtk4Terminal
                if isinstance(term, Gtk4Terminal):
                    if opts.working_directory:
                        cwd = opts.working_directory
                    else:
                        cwd = None
                    if opts.execute:
                        argv = opts.execute if isinstance(opts.execute, list) else [opts.execute]
                        term.spawn_command(argv, cwd)
                    elif opts.command:
                        argv = [opts.command]
                        term.spawn_command(argv, cwd)
                    else:
                        term.spawn_login_shell(cwd)
            except Exception:
                pass

        win.present()

    def run(self, argv: Optional[List[str]] = None) -> int:
        # Match Gtk.Application.run signature expecting a list of strings
        if argv is None:
            argv = []
        return super().run(argv)
