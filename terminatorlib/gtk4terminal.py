"""Minimal GTK4 Vte terminal wrapper."""

import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk, GLib, Vte, Gio


def _find_user_shell() -> str:
    # Basic shell lookup without importing legacy Gtk3-bound util module
    try:
        import pwd
        shell = pwd.getpwuid(os.getuid()).pw_shell
        if shell and os.path.exists(shell):
            return shell
    except Exception:
        pass
    for cand in (os.environ.get('SHELL'), '/bin/bash', '/bin/zsh', '/bin/sh'):
        if cand and os.path.exists(cand):
            return cand
    return '/bin/sh'


class Gtk4Terminal(Vte.Terminal):
    def __init__(self):
        super().__init__()
        self.set_scroll_on_output(False)
        self.set_scroll_on_keystroke(True)
        # Reasonable defaults; broader settings migration will come later
        self.set_allow_hyperlink(True)
        self.set_mouse_autohide(True)

    def spawn_login_shell(self, cwd: str | None = None):
        if cwd is None:
            cwd = os.getcwd()
        pty_flags = Vte.PtyFlags.DEFAULT
        shell = _find_user_shell()
        argv = [shell]
        envv = [f"{k}={v}" for k, v in os.environ.items()]

        def _on_spawned(term, task, user_data):
            try:
                term.spawn_async_finish(task)
            except Exception as ex:
                print(f"Failed to spawn shell: {ex}")

        self.spawn_async(
            pty_flags,
            cwd,
            argv,
            envv,
            GLib.SpawnFlags.SEARCH_PATH,
            None,           # child_setup
            None,           # child_setup_data
            -1,             # timeout
            None,           # cancellable
            _on_spawned,    # callback
            None,           # user_data
        )
