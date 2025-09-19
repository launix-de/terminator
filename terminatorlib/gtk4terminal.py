"""Minimal GTK4 Vte terminal wrapper."""

import os
from gi.repository import Gtk, GLib, Vte, Gio
from .config import Config


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
        self._scroller = None
        self._install_context_menu()

    def spawn_login_shell(self, cwd: str | None = None):
        if cwd is None:
            cwd = os.getcwd()
        pty_flags = Vte.PtyFlags.DEFAULT
        shell = _find_user_shell()
        argv = [shell]
        envv = [f"{k}={v}" for k, v in os.environ.items()]

        def _on_spawned(*cb_args):
            try:
                # New VTE GTK4 callback typically provides (term, pid, error, user_data)
                if len(cb_args) >= 3:
                    # cb_args[2] may be error or result depending on binding; handle error if present
                    err = cb_args[2]
                    if err:
                        # err can be a GError or AsyncResult depending on GI; just print
                        print(f"Failed to spawn shell: {err}")
                        return
                # If no error, consider spawn successful
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

    def spawn_command(self, argv, cwd: str | None = None, env: dict | None = None):
        if cwd is None:
            cwd = os.getcwd()
        if not argv or not isinstance(argv, (list, tuple)):
            return self.spawn_login_shell(cwd)
        pty_flags = Vte.PtyFlags.DEFAULT
        envv = [f"{k}={v}" for k, v in (env or os.environ).items()]

        def _on_spawned(*cb_args):
            try:
                if len(cb_args) >= 3:
                    err = cb_args[2]
                    if err:
                        print(f"Failed to spawn command: {err}")
                        return
            except Exception as ex:
                print(f"Failed to spawn command: {ex}")

        self.spawn_async(
            pty_flags,
            cwd,
            list(argv),
            envv,
            GLib.SpawnFlags.SEARCH_PATH,
            None,
            None,
            -1,
            None,
            _on_spawned,
            None,
        )

    def set_scroller(self, scroller: Gtk.ScrolledWindow):
        self._scroller = scroller

    # Context menu (right-click) using GtkPopoverMenu
    def _install_context_menu(self):
        from gi.repository import Gdk
        self._menu = Gio.Menu()
        self._popover = Gtk.PopoverMenu.new_from_model(self._menu)
        self._popover.set_parent(self)

        # Add actions on the widget so the menu can trigger them
        action_group = Gio.SimpleActionGroup()
        self._action_group = action_group

        act_copy = Gio.SimpleAction.new("copy", None)
        act_copy.connect("activate", lambda a, p: self.copy_clipboard())
        action_group.add_action(act_copy)

        act_paste = Gio.SimpleAction.new("paste", None)
        act_paste.connect("activate", lambda a, p: self.paste_clipboard())
        action_group.add_action(act_paste)

        act_close = Gio.SimpleAction.new("close", None)
        def _do_close(a, p):
            toplevel = self.get_root()
            if isinstance(toplevel, Gtk.Window):
                toplevel.close()
        act_close.connect("activate", _do_close)
        action_group.add_action(act_close)

        # Toggle read-only
        # initial readonly state reflects current input_enabled inverse
        ro_initial = not self.get_input_enabled()
        act_ro = Gio.SimpleAction.new_stateful("toggle_readonly", None, GLib.Variant('b', ro_initial))
        def on_ro(action, value):
            action.set_state(value)
            enabled = not value.get_boolean()
            try:
                self.set_input_enabled(enabled)
            except Exception:
                pass
        act_ro.connect("change-state", on_ro)
        action_group.add_action(act_ro)

        # Toggle scrollbar
        sb_initial = True
        act_sb = Gio.SimpleAction.new_stateful("toggle_scrollbar", None, GLib.Variant('b', sb_initial))
        def on_sb(action, value):
            action.set_state(value)
            if self._scroller is not None:
                self._scroller.set_policy(Gtk.PolicyType.NEVER if not value.get_boolean() else Gtk.PolicyType.AUTOMATIC,
                                          Gtk.PolicyType.AUTOMATIC)
                self._scroller.set_overlay_scrolling(value.get_boolean())
        act_sb.connect("change-state", on_sb)
        action_group.add_action(act_sb)

        # Zoom (placeholder) and Maximize
        act_zoom = Gio.SimpleAction.new("zoom", None)
        def on_zoom(a, p):
            win = self.get_root()
            if hasattr(win, 'zoom_terminal'):
                win.zoom_terminal(self)
        act_zoom.connect("activate", on_zoom)
        action_group.add_action(act_zoom)

        act_max = Gio.SimpleAction.new("maximize", None)
        def on_maximize(a, p):
            toplevel = self.get_root()
            if isinstance(toplevel, Gtk.Window):
                toplevel.maximize()
        act_max.connect("activate", on_maximize)
        action_group.add_action(act_max)

        # Set window title
        act_title = Gio.SimpleAction.new("edit_window_title", None)
        def on_edit_title(a, p):
            win = self.get_root()
            if not isinstance(win, Gtk.Window):
                return
            dialog = Gtk.Dialog(title="Set Window Title", transient_for=win, modal=True)
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
                        win.set_title(txt)
                dlg.destroy()
            dialog.connect("response", on_response)
            dialog.present()
        act_title.connect("activate", on_edit_title)
        action_group.add_action(act_title)

        # Preferences
        act_prefs = Gio.SimpleAction.new("preferences", None)
        def on_prefs(a, p):
            from .preferences_gtk4 import PreferencesWindow
            win = self.get_root() if isinstance(self.get_root(), Gtk.Window) else None
            dlg = PreferencesWindow(parent=win)
            dlg.present()
        act_prefs.connect("activate", on_prefs)
        action_group.add_action(act_prefs)

        self.insert_action_group("term", action_group)

        # Right-click gesture
        click = Gtk.GestureClick.new()
        click.set_button(3)

        def on_pressed(gesture, n_press, x, y):
            # Rebuild model to reflect current state
            self._build_menu_model()
            # Position popover at click point
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = rect.height = 1
            self._popover.set_pointing_to(rect)
            self._popover.popup()

        click.connect("pressed", on_pressed)
        self.add_controller(click)

    def _build_menu_model(self):
        menu = Gio.Menu()
        # URL actions would require regex checks; keep core items for now
        section = Gio.Menu()
        section.append("Copy", "term.copy")
        section.append("Copy as HTML", "term.copy_html")  # not yet implemented
        section.append("Paste", "term.paste")
        menu.append_section(None, section)

        section2 = Gio.Menu()
        section2.append("Split Auto", "term.split_auto")
        section2.append("Split Horizontally", "term.split_horiz")
        section2.append("Split Vertically", "term.split_vert")
        section2.append("Open Tab", "term.new_tab")
        section2.append("Set Window Title", "term.edit_window_title")
        section2.append("Close", "term.close")
        menu.append_section(None, section2)

        section3 = Gio.Menu()
        section3.append("Zoom terminal", "term.zoom")
        section3.append("Maximize terminal", "term.maximize")
        menu.append_section(None, section3)

        section4 = Gio.Menu()
        section4.append("Read only", "term.toggle_readonly")
        section4.append("Show scrollbar", "term.toggle_scrollbar")
        section4.append("Preferences", "term.preferences")

        # Profiles submenu
        cfg = Config()
        profiles = sorted(cfg.list_profiles(), key=str.lower)
        if len(profiles) > 1:
            profiles_menu = Gio.Menu()
            for p in profiles:
                item = Gio.MenuItem.new(p, None)
                item.set_attribute_value("action", GLib.Variant.new_string("term.profile"))
                item.set_attribute_value("target", GLib.Variant.new_string(p))
                profiles_menu.append_item(item)
            section4.append_submenu("Profiles", profiles_menu)

        # Layouts submenu
        try:
            layouts = cfg.list_layouts()
            if layouts:
                layouts_menu = Gio.Menu()
                for lay in layouts:
                    item = Gio.MenuItem.new(lay, None)
                    item.set_attribute_value("action", GLib.Variant.new_string("term.layout"))
                    item.set_attribute_value("target", GLib.Variant.new_string(lay))
                    layouts_menu.append_item(item)
                section4.append_submenu("Layouts...", layouts_menu)
        except Exception:
            pass

        menu.append_section(None, section4)

        # Connect actions for profiles/layouts
        ag = self._action_group.lookup_action("profile")
        if ag is None:
            ag = Gio.SimpleAction.new("profile", GLib.VariantType.new("s"))
            ag.connect("activate", self._on_profile_activate)
            self._action_group.add_action(ag)
        ag2 = self._action_group.lookup_action("layout")
        if ag2 is None:
            ag2 = Gio.SimpleAction.new("layout", GLib.VariantType.new("s"))
            ag2.connect("activate", self._on_layout_activate)
            self._action_group.add_action(ag2)

        # Copy HTML action placeholder
        if self._action_group.lookup_action("copy_html") is None:
            self._action_group.add_action(Gio.SimpleAction.new("copy_html", None))
        # Split / new tab actions routed to the window
        if self._action_group.lookup_action("split_horiz") is None:
            act = Gio.SimpleAction.new("split_horiz", None)
            act.connect("activate", lambda a, p: self._request_split(Gtk.Orientation.HORIZONTAL))
            self._action_group.add_action(act)
        if self._action_group.lookup_action("split_vert") is None:
            act = Gio.SimpleAction.new("split_vert", None)
            act.connect("activate", lambda a, p: self._request_split(Gtk.Orientation.VERTICAL))
            self._action_group.add_action(act)
        if self._action_group.lookup_action("split_auto") is None:
            act = Gio.SimpleAction.new("split_auto", None)
            # Prefer vertical for wide windows
            act.connect("activate", lambda a, p: self._request_split(Gtk.Orientation.VERTICAL))
            self._action_group.add_action(act)
        if self._action_group.lookup_action("new_tab") is None:
            act = Gio.SimpleAction.new("new_tab", None)
            act.connect("activate", lambda a, p: self._request_new_tab())
            self._action_group.add_action(act)

        self._menu = menu
        self._popover.set_menu_model(self._menu)

    def _on_profile_activate(self, action, param):
        profile = param.get_string() if param else None
        if not profile:
            return
        try:
            cfg = Config()
            if profile in cfg.list_profiles():
                cfg.set_profile(profile, True)
        except Exception:
            pass

    def _on_layout_activate(self, action, param):
        layout = param.get_string() if param else None
        if not layout:
            return
        try:
            import sys, subprocess
            cmd = sys.argv[0]
            if not os.path.isabs(cmd):
                cmd = os.path.join(os.getcwd(), cmd)
            if not os.path.isfile(cmd):
                return
            subprocess.Popen([cmd, '-u', '-l', layout])
        except Exception:
            pass

    def _request_split(self, orientation: Gtk.Orientation):
        win = self.get_root()
        if hasattr(win, 'split_terminal'):
            win.split_terminal(self, orientation)

    def _request_new_tab(self):
        win = self.get_root()
        if hasattr(win, 'open_new_tab'):
            win.open_new_tab()
