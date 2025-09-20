"""Minimal GTK4 Vte terminal wrapper."""

import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk, GLib, Vte, Gio, Gdk
from .translation import _
from gi.repository import Pango
from gi.repository import Pango
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
        # Assign a uuid for layout serialization and grouping
        try:
            import uuid as _uuid
            self.uuid = str(_uuid.uuid4())
        except Exception:
            self.uuid = None
        # Map of plugin handler names to VTE match tag ids
        self._plugin_match_tags = {}
        # Reverse map from tag id to handler instance for transformation
        self._plugin_tag_handlers = {}
        # Per-terminal config (shares base via Borg, but profile is per-instance)
        self.config = Config()
        self.set_scroll_on_output(False)
        self.set_scroll_on_keystroke(True)
        # Reasonable defaults; broader settings migration will come later
        self.set_allow_hyperlink(True)
        self.set_mouse_autohide(True)
        self._scroller = None
        self._font_scale = 1.0
        self._install_context_menu()
        self._install_url_handling()
        self._copy_on_sel_handler = None
        # Update window/tab titles on VTE title changes
        try:
            self.connect('window-title-changed', self._on_window_title_changed)
        except Exception:
            pass
        # Some shells/apps use icon-title; update on that as well
        try:
            self.connect('icon-title-changed', self._on_window_title_changed)
        except Exception:
            pass
        try:
            self.connect('bell', self._on_bell)
        except Exception:
            pass
        # Search state
        self._search_last_kind = None  # 'vte' | 'glib'
        self._search_is_regex = False
        self._search_case_sensitive = True
        # Selection copy-on-select (optional)
        try:
            if bool(self.config['copy_on_selection']) and self._copy_on_sel_handler is None:
                try:
                    self._copy_on_sel_handler = self.connect('selection-changed', self._on_selection_changed_copy)
                except Exception:
                    self._copy_on_sel_handler = None
        except Exception:
            pass
        # Track selection to enable/disable copy actions live
        try:
            self.connect('selection-changed', self._on_selection_changed_actions)
        except Exception:
            pass
        # Install plugin URL handler regexes on this terminal (for hover/match behavior)
        try:
            self._install_plugin_url_matches()
        except Exception:
            pass
        # Apply current profile settings to this terminal
        try:
            self.apply_profile()
        except Exception:
            pass
        # Focus controller to notify window for RX/TX visuals
        try:
            fctrl = Gtk.EventControllerFocus()
            def on_enter(ctrl):
                win = self.get_root()
                if hasattr(win, '_on_terminal_focus_changed'):
                    win._on_terminal_focus_changed(self, True)
            def on_leave(ctrl):
                win = self.get_root()
                if hasattr(win, '_on_terminal_focus_changed'):
                    win._on_terminal_focus_changed(self, False)
            fctrl.connect('enter', lambda c: on_enter(c))
            fctrl.connect('leave', lambda c: on_leave(c))
            self.add_controller(fctrl)
        except Exception:
            pass

        # Monitor clipboard changes to enable/disable paste actions
        try:
            disp = self.get_display()
            if disp is not None:
                cb = disp.get_clipboard()
                try:
                    cb.connect('changed', lambda *_a: self._update_clipboard_actions())
                except Exception:
                    pass
                try:
                    pcb = disp.get_primary_clipboard()
                    pcb.connect('changed', lambda *_a: self._update_clipboard_actions())
                except Exception:
                    pass
                # Initialize action states
                self._update_clipboard_actions()
        except Exception:
            pass

    def _install_url_handling(self):
        # Install a URL regex and simple Ctrl+Click opener with hover cursor
        self._ctrl_down = False
        self._url_tag = None
        try:
            from .config import Config
            self._link_single_click = bool(Config()['link_single_click'])
        except Exception:
            self._link_single_click = True
        # Common URL regex pattern (simplified)
        url_pattern = r"(https?|ftp)://[^\s<>]+"
        try:
            rx = Vte.Regex.new_for_match(url_pattern, 0, 0)
            if hasattr(self, 'match_add_regex'):
                self._url_tag = self.match_add_regex(rx, 0)
            elif hasattr(self, 'match_add'):  # older symbol name
                self._url_tag = self.match_add(rx, 0)
        except Exception:
            self._url_tag = None

        # Track Ctrl key state
        try:
            kctrl = Gtk.EventControllerKey()
            def on_key_pressed(ctrl, keyval, keycode, state):
                from gi.repository import Gdk
                if state & Gdk.ModifierType.CONTROL_MASK or keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R):
                    self._ctrl_down = True
                return False
            def on_key_released(ctrl, keyval, keycode, state):
                from gi.repository import Gdk
                if keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R):
                    self._ctrl_down = False
                # If no modifier mask remains, clear flag
                if not (state & Gdk.ModifierType.CONTROL_MASK):
                    self._ctrl_down = False
                return False
            kctrl.connect('key-pressed', on_key_pressed)
            kctrl.connect('key-released', on_key_released)
            self.add_controller(kctrl)
        except Exception:
            pass

        # Ctrl + mouse wheel zoom
        try:
            scr = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
            def on_scroll(controller, dx, dy):
                # Only handle when Ctrl is held, and feature not disabled in profile
                if getattr(self, '_zoom_wheel_disabled', False):
                    return False
                if not getattr(self, '_ctrl_down', False):
                    return False
                try:
                    if dy < 0:
                        self.zoom_step(0.1)
                    elif dy > 0:
                        self.zoom_step(-0.1)
                except Exception:
                    pass
                return True
            scr.connect('scroll', on_scroll)
            self.add_controller(scr)
        except Exception:
            pass

        # Change cursor when hovering links while holding Ctrl
        try:
            mctrl = Gtk.EventControllerMotion()
            def on_motion(ctrl, x, y):
                self._update_link_cursor(x, y)
            mctrl.connect('motion', on_motion)
            # Sloppy focus: focus terminal when pointer enters if configured
            try:
                def on_enter(ctrl, x, y):
                    self._maybe_sloppy_focus()
                mctrl.connect('enter', on_enter)
            except Exception:
                pass
            self.add_controller(mctrl)
        except Exception:
            pass

        # Ctrl+Click to open link
        try:
            click = Gtk.GestureClick.new()
            click.set_button(1)
            def on_released(gesture, n_press, x, y):
                if not self._ctrl_down:
                    return
                # If single-click disabled, require double-click
                if not self._link_single_click and int(n_press) < 2:
                    return
                uri = self._uri_at_point(x, y)
                if uri:
                    try:
                        Gio.AppInfo.launch_default_for_uri(uri)
                    except Exception:
                        pass
            click.connect('released', on_released)
            self.add_controller(click)
        except Exception:
            pass

    def _maybe_sloppy_focus(self):
        try:
            sloppy = False
            try:
                if self.config.get_system_focus() in ['sloppy', 'mouse']:
                    sloppy = True
            except Exception:
                pass
            if not sloppy:
                try:
                    if self.config['focus'] in ['sloppy', 'mouse']:
                        sloppy = True
                except Exception:
                    pass
            if sloppy:
                self.grab_focus()
        except Exception:
            pass

        # Optionally disable middle-click paste
        try:
            mid = Gtk.GestureClick.new()
            mid.set_button(2)
            try:
                mid.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            except Exception:
                pass
            def on_mid_pressed(gesture, n_press, x, y):
                try:
                    from .config import Config as _Cfg
                    if bool(_Cfg()['disable_mouse_paste']):
                        try:
                            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                        except Exception:
                            pass
                        return
                except Exception:
                    pass
            mid.connect('pressed', on_mid_pressed)
            self.add_controller(mid)
        except Exception:
            pass

    def _uri_at_point(self, x: float, y: float) -> str | None:
        # Resolve matched text at location; try multiple APIs for robustness
        try:
            # VTE exposes match_check at cell coords; translate from pixels if needed
            if hasattr(self, 'convert_pixels_to_cell'):  # new helper
                col, row = self.convert_pixels_to_cell(int(x), int(y))
                res = self.match_check(col, row)
            elif hasattr(self, 'match_check'):  # some bindings accept (x,y)
                try:
                    res = self.match_check(int(x), int(y))
                except TypeError:
                    # Try column/row path if available
                    col = getattr(self, 'get_column_count')() // 2
                    row = getattr(self, 'get_row_count')() // 2
                    res = self.match_check(col, row)
            else:
                res = None
            if isinstance(res, (list, tuple)) and res:
                # Commonly returns (matched_string, tag)
                s = res[0]
                tag = None
                try:
                    tag = int(res[1]) if len(res) > 1 else None
                except Exception:
                    tag = None
                if isinstance(s, str):
                    if s.startswith('http://') or s.startswith('https://') or s.startswith('ftp://'):
                        return s
                    # If this match came from a plugin handler, transform using its callback
                    if tag is not None and tag in getattr(self, '_plugin_tag_handlers', {}):
                        try:
                            handler = self._plugin_tag_handlers.get(tag)
                            final = handler.callback(s)
                            if isinstance(final, str) and final:
                                return final
                        except Exception:
                            pass
        except Exception:
            pass
        # Fallback: probe a small rectangle around the point and extract with get_text_range
        try:
            if hasattr(self, 'convert_pixels_to_cell'):
                col, row = self.convert_pixels_to_cell(int(x), int(y))
            else:
                col = row = 0
            rng = self.get_text_range(max(0, row-0), 0, row, getattr(self, 'get_column_count')()-1)
            if isinstance(rng, (list, tuple)) and rng and rng[0]:
                import re as _re
                m = _re.search(r"(https?|ftp)://[^\s<>]+", rng[0])
                if m:
                    return m.group(0)
        except Exception:
            pass
        return None

    def _update_link_cursor(self, x: float, y: float):
        try:
            from gi.repository import Gdk
            uri = self._uri_at_point(x, y) if self._ctrl_down else None
            if hasattr(self, 'set_cursor'):
                if uri:
                    disp = self.get_display()
                    if disp is None:
                        return
                    cursor = Gdk.Cursor.new_from_name(disp, 'pointer')
                    self.set_cursor(cursor)
                    try:
                        self.set_tooltip_text(uri)
                    except Exception:
                        pass
                    try:
                        # Add CSS class to allow hover styling from theme
                        if 'vte-link-hover' not in self.get_css_classes():
                            self.add_css_class('vte-link-hover')
                    except Exception:
                        pass
                else:
                    self.set_cursor(None)
                    try:
                        self.set_tooltip_text(None)
                    except Exception:
                        pass
                    try:
                        if 'vte-link-hover' in self.get_css_classes():
                            self.remove_css_class('vte-link-hover')
                    except Exception:
                        pass
        except Exception:
            pass

    def spawn_login_shell(self, cwd: str | None = None):
        if cwd is None:
            cwd = os.getcwd()
        pty_flags = Vte.PtyFlags.DEFAULT
        # Build argv from profile settings
        prof = {}
        try:
            prof = self.config.get_profile_by_name(self.config.get_profile())
        except Exception:
            prof = {}
        use_custom = bool(prof.get('use_custom_command', False))
        custom_cmd = str(prof.get('custom_command', '') or '')
        login_shell = bool(prof.get('login_shell', False))
        if use_custom and custom_cmd:
            try:
                import shlex as _shlex
                argv = _shlex.split(custom_cmd)
            except Exception:
                argv = [custom_cmd]
        else:
            shell = _find_user_shell()
            argv = [shell]
            if login_shell:
                argv.append('-l')
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

    # Compatibility helpers for plugins
    def get_cwd(self) -> str:
        try:
            uri = self.get_current_directory_uri()
            if uri and isinstance(uri, str):
                if uri.startswith('file://'):
                    return uri[len('file://'):]
                return uri
        except Exception:
            pass
        try:
            return os.getcwd()
        except Exception:
            return ''

    def open_url(self, url: str):
        try:
            from .config import Config as _Cfg
            cfg = _Cfg()
            use_custom = bool(cfg['use_custom_url_handler'])
            cmd = str(cfg['custom_url_handler'] or '').strip()
        except Exception:
            use_custom = False
            cmd = ''
        if use_custom and cmd:
            try:
                # Support %s placeholder; else append url
                if '%s' in cmd:
                    full = cmd.replace('%s', url)
                    args = full
                else:
                    args = cmd + ' ' + url
                # Spawn via Gio.Subprocess without blocking
                sp = Gio.Subprocess.new(['bash','-lc', args], Gio.SubprocessFlags.NONE)
                # Do not wait
                return
            except Exception:
                pass
        try:
            Gio.AppInfo.launch_default_for_uri(url)
        except Exception:
            pass

    # GTK3-compat for plugin URLHandler API
    def match_add(self, handler_name: str, pattern: str):
        try:
            rx = None
            try:
                rx = Vte.Regex.new_for_match(pattern, 0, 0)
            except Exception:
                rx = None
            if rx is None:
                return -1
            tag = None
            if hasattr(self, 'match_add_regex'):
                tag = self.match_add_regex(rx, 0)
            elif hasattr(self, 'match_add'):
                tag = self.match_add(rx, 0)
            if tag is not None:
                self._plugin_match_tags[str(handler_name)] = int(tag)
                return int(tag)
        except Exception:
            pass
        return -1

    def match_remove(self, handler_name_or_tag):
        try:
            tag = None
            if isinstance(handler_name_or_tag, int):
                tag = handler_name_or_tag
            else:
                tag = self._plugin_match_tags.get(str(handler_name_or_tag))
            if tag is None:
                return
            if hasattr(self, 'match_remove'):
                # Some bindings expose match_remove(tag)
                try:
                    super().match_remove(int(tag))
                except Exception:
                    pass
            # Clean mapping
            try:
                for k, v in list(self._plugin_match_tags.items()):
                    if v == tag or k == handler_name_or_tag:
                        del self._plugin_match_tags[k]
            except Exception:
                pass
        except Exception:
            pass

    # Many GTK3-era plugins expect Terminal.get_vte()
    def get_vte(self):
        return self

    # GTK3 compatibility shims for plugins
    def get_toplevel(self):
        try:
            return self.get_root()
        except Exception:
            return None

    def get_window_title(self):
        """Return the VTE-provided window title for this terminal.

        Matches GTK3 behavior which reads the terminal's own title (OSC 0/2),
        not the application window title.
        """
        try:
            # Prefer explicit Vte.Terminal API
            title = Vte.Terminal.get_window_title(self)
            if title:
                return title
        except Exception:
            pass
        try:
            icon = Vte.Terminal.get_icon_title(self)
            if icon:
                return icon
        except Exception:
            pass
        return ''

    def set_profile(self, _sender=None, profile: str | None = None):
        try:
            if profile:
                self.config.set_profile(profile, True)
                self.apply_profile()
        except Exception:
            pass

    def get_profile(self) -> str:
        try:
            return self.config.get_profile()
        except Exception:
            return 'default'

    def _on_selection_changed_copy(self, *args):
        try:
            # Prefer primary selection if supported by VTE, else regular
            if hasattr(self, 'copy_primary'):
                self.copy_primary()
            else:
                self.copy_clipboard()
        except Exception:
            pass

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
        self._rclick_xy = (0.0, 0.0)

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
            # Close only the current terminal, not the whole window
            win = self.get_root()
            if hasattr(win, '_on_close_term'):
                try:
                    win._on_close_term()
                    return
                except Exception:
                    pass
            # Fallback: try to exit the shell
            try:
                self.feed_child("exit\n")
            except Exception:
                pass
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

        # Toggle scrollbar (hide both bars and disable overlay when off)
        sb_initial = True
        act_sb = Gio.SimpleAction.new_stateful("toggle_scrollbar", None, GLib.Variant('b', sb_initial))
        def on_sb(action, value):
            action.set_state(value)
            if self._scroller is not None:
                show = bool(value.get_boolean())
                self._scroller.set_policy(Gtk.PolicyType.AUTOMATIC if show else Gtk.PolicyType.NEVER,
                                          Gtk.PolicyType.AUTOMATIC if show else Gtk.PolicyType.NEVER)
                try:
                    self._scroller.set_overlay_scrolling(show)
                except Exception:
                    pass
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
            try:
                self._rclick_xy = (float(x), float(y))
            except Exception:
                self._rclick_xy = (0.0, 0.0)
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
        from .terminal_popup_menu_gtk4 import build_menu_model
        # Ensure actions exist
        if self._action_group.lookup_action("copy_html") is None:
            self._action_group.add_action(Gio.SimpleAction.new("copy_html", None))
        # Update copy/copy_html sensitivity based on selection state if possible
        try:
            has_sel = False
            if hasattr(self, 'get_has_selection'):
                has_sel = bool(self.get_has_selection())
            a_copy = self._action_group.lookup_action('copy')
            a_html = self._action_group.lookup_action('copy_html')
            if a_copy is not None:
                a_copy.set_enabled(has_sel)
            if a_html is not None:
                a_html.set_enabled(has_sel)
        except Exception:
            pass
        for a in ("split_horiz","split_vert","split_auto","new_tab"):
            if self._action_group.lookup_action(a) is None:
                act = Gio.SimpleAction.new(a, None)
                if a == 'split_horiz':
                    act.connect('activate', lambda *args: self._request_split(Gtk.Orientation.HORIZONTAL))
                elif a == 'split_vert':
                    act.connect('activate', lambda *args: self._request_split(Gtk.Orientation.VERTICAL))
                elif a == 'split_auto':
                    act.connect('activate', lambda *args: self._request_split_auto())
                elif a == 'new_tab':
                    act.connect('activate', lambda *args: self._request_new_tab())
                self._action_group.add_action(act)
        # Edit tab title action
        if self._action_group.lookup_action('edit_tab_title') is None:
            act = Gio.SimpleAction.new('edit_tab_title', None)
            def on_edit_tab_title(a, p):
                win = self.get_root()
                if hasattr(win, '_on_edit_tab_title'):
                    win._on_edit_tab_title()
            act.connect('activate', on_edit_tab_title)
            self._action_group.add_action(act)
        # Search action opens a popover anchored to the terminal
        if self._action_group.lookup_action('search') is None:
            act = Gio.SimpleAction.new('search', None)
            act.connect('activate', lambda *a: self._show_search_popover())
            self._action_group.add_action(act)
        # Find next/previous actions
        if self._action_group.lookup_action('find_next') is None:
            a = Gio.SimpleAction.new('find_next', None)
            a.connect('activate', lambda *aa: self._search_find(True))
            self._action_group.add_action(a)
        if self._action_group.lookup_action('find_previous') is None:
            a = Gio.SimpleAction.new('find_previous', None)
            a.connect('activate', lambda *aa: self._search_find(False))
            self._action_group.add_action(a)
        # Help
        if self._action_group.lookup_action('help') is None:
            a = Gio.SimpleAction.new('help', None)
            a.connect('activate', lambda *aa: (getattr(self.get_root(), '_on_help', lambda *a: None)()))
            self._action_group.add_action(a)
        # Paste selection, reset, reset_clear, full_screen, new_window, hide_window
        def win_call(method):
            w = self.get_root()
            return getattr(w, method, None)
        def add_simple_action(name, cb):
            if self._action_group.lookup_action(name) is None:
                a = Gio.SimpleAction.new(name, None)
                a.connect('activate', cb)
                self._action_group.add_action(a)
        add_simple_action('paste_selection', lambda *a: win_call('_on_paste_selection') and win_call('_on_paste_selection')())
        add_simple_action('reset', lambda *a: win_call('_on_reset_terminal') and win_call('_on_reset_terminal')())
        add_simple_action('reset_clear', lambda *a: win_call('_on_reset_clear_terminal') and win_call('_on_reset_clear_terminal')())
        add_simple_action('full_screen', lambda *a: win_call('_on_full_screen') and win_call('_on_full_screen')())
        add_simple_action('new_window', lambda *a: win_call('_on_new_window') and win_call('_on_new_window')())
        add_simple_action('hide_window', lambda *a: win_call('_on_hide_window') and win_call('_on_hide_window')())
        # Grouping related actions
        def add_simple(name, cb):
            if self._action_group.lookup_action(name) is None:
                a = Gio.SimpleAction.new(name, None)
                a.connect('activate', cb)
                self._action_group.add_action(a)
        def win_call(method):
            win = self.get_root()
            return getattr(win, method, None)
        add_simple('create_group', lambda *a: self._show_group_popover())
        add_simple('group_all_window', lambda *a: win_call('_group_all_window') and win_call('_group_all_window')(self))
        add_simple('ungroup_all_window', lambda *a: win_call('_ungroup_all_window') and win_call('_ungroup_all_window')(self))
        add_simple('group_all_tab', lambda *a: win_call('_group_all_tab') and win_call('_group_all_tab')(self))
        add_simple('ungroup_all_tab', lambda *a: win_call('_ungroup_all_tab') and win_call('_ungroup_all_tab')(self))
        add_simple('groupsend_off', lambda *a: win_call('_set_groupsend') and win_call('_set_groupsend')('off'))
        add_simple('groupsend_group', lambda *a: win_call('_set_groupsend') and win_call('_set_groupsend')('group'))
        add_simple('groupsend_all', lambda *a: win_call('_set_groupsend') and win_call('_set_groupsend')('all'))
        # profile/layout actions
        if self._action_group.lookup_action('profile') is None:
            # Stateful string action so menu shows radio items for profiles
            try:
                current = self.config.get_profile()
            except Exception:
                current = 'default'
            ag = Gio.SimpleAction.new_stateful('profile', GLib.VariantType.new('s'), GLib.Variant('s', current))
            def on_change(action, value):
                try:
                    profile = value.get_string()
                    if profile and profile in self.config.list_profiles():
                        self.config.set_profile(profile, True)
                        self.apply_profile()
                        action.set_state(value)
                except Exception:
                    pass
            ag.connect('change-state', on_change)
            self._action_group.add_action(ag)
        if self._action_group.lookup_action('layout') is None:
            ag2 = Gio.SimpleAction.new('layout', GLib.VariantType.new('s'))
            ag2.connect('activate', self._on_layout_activate)
            self._action_group.add_action(ag2)

        base_menu = build_menu_model(self)
        # If right-clicked over a URL, offer quick actions first
        quick_menu = None
        url = None
        try:
            x, y = self._rclick_xy
            url = self._uri_at_point(x, y)
        except Exception:
            url = None
        if url:
            # Ensure actions exist
            if self._action_group.lookup_action('open_link') is None:
                act = Gio.SimpleAction.new('open_link', None)
                def on_open(_a, _p):
                    try:
                        self.open_url(url)
                    except Exception:
                        pass
                act.connect('activate', on_open)
                self._action_group.add_action(act)
            if self._action_group.lookup_action('copy_link') is None:
                act2 = Gio.SimpleAction.new('copy_link', None)
                def on_copy(_a, _p):
                    try:
                        disp = self.get_display()
                        if disp is not None:
                            cb = disp.get_clipboard()
                            cb.set_text(url)
                    except Exception:
                        pass
                act2.connect('activate', on_copy)
                self._action_group.add_action(act2)
            quick_menu = Gio.Menu()
            sec = Gio.Menu()
            try:
                from .translation import _
                sec.append(_('Open _Link'), 'term.open_link')
                sec.append(_('Copy Link _Address'), 'term.copy_link')
            except Exception:
                sec.append('Open Link', 'term.open_link')
                sec.append('Copy Link Address', 'term.copy_link')
            quick_menu.append_section(None, sec)
        else:
            # If not a standard URL, try plugin URL handlers (e.g., lp:12345)
            try:
                x, y = self._rclick_xy
                plug = self._plugin_url_action_at_point(x, y)
            except Exception:
                plug = None
            if plug is not None:
                open_label, copy_label, final_url = plug
                # Install actions bound to this resolved URL
                if self._action_group.lookup_action('open_link') is None:
                    act = Gio.SimpleAction.new('open_link', None)
                    act.connect('activate', lambda *_a: self.open_url(final_url))
                    self._action_group.add_action(act)
                else:
                    # Rebind by removing and re-adding with new callback is tricky; rely on capturing variable
                    pass
                if self._action_group.lookup_action('copy_link') is None:
                    act2 = Gio.SimpleAction.new('copy_link', None)
                    def on_copy2(_a, _p):
                        try:
                            disp = self.get_display()
                            if disp is not None:
                                cb = disp.get_clipboard()
                                cb.set_text(final_url)
                        except Exception:
                            pass
                    act2.connect('activate', on_copy2)
                    self._action_group.add_action(act2)
                quick_menu = Gio.Menu()
                sec = Gio.Menu()
                sec.append(open_label, 'term.open_link')
                sec.append(copy_label, 'term.copy_link')
                quick_menu.append_section(None, sec)

        if quick_menu is not None:
            mixed = Gio.Menu()
            # Append quick section, then the rest
            for i in range(quick_menu.get_n_items()):
                sub = quick_menu.get_item_link(i, Gio.MENU_LINK_SECTION)
                if sub is not None:
                    mixed.append_section(None, sub)
            mixed.append_section(None, base_menu)
            self._menu = mixed
        else:
            self._menu = base_menu
        self._popover.set_menu_model(self._menu)

        # Connect copy_html action to handler
        act_html = self._action_group.lookup_action('copy_html')
        if act_html is not None and not hasattr(act_html, '_connected_html'):
            def on_copy_html(_a, _p):
                try:
                    self.copy_selection_as_html()
                    # Clear selection after copy if configured
                    try:
                        from .config import Config as _Cfg
                        if bool(_Cfg()['clear_select_on_copy']) and hasattr(self, 'unselect_all'):
                            self.unselect_all()
                    except Exception:
                        pass
                except Exception:
                    pass
            act_html.connect('activate', on_copy_html)
            setattr(act_html, '_connected_html', True)
        # Ensure paste actions are enabled/disabled per clipboard
        try:
            self._update_clipboard_actions()
        except Exception:
            pass

    def _plugin_url_action_at_point(self, x: float, y: float):
        # Probe text around pointer row and try URL handler plugins
        try:
            # Determine row and grab full line text
            if hasattr(self, 'convert_pixels_to_cell'):
                col, row = self.convert_pixels_to_cell(int(x), int(y))
            else:
                row = 0
            total_cols = getattr(self, 'get_column_count')() if hasattr(self, 'get_column_count') else 0
            if total_cols <= 0:
                total_cols = 200
            rng = self.get_text_range(max(0, row), 0, row, max(0, total_cols - 1))
            line = rng[0] if isinstance(rng, (list, tuple)) and rng else ''
        except Exception:
            line = ''
        if not line:
            return None
        try:
            from .plugin import PluginRegistry
            import re as _re
            reg = PluginRegistry()
            reg.load_plugins(force=True, capabilities_filter={'url_handler'})
            handlers = reg.get_plugins_by_capability('url_handler')
        except Exception:
            handlers = []
        for h in handlers:
            try:
                pat = getattr(h, 'match', None)
                if not pat:
                    continue
                m = _re.search(pat, line)
                if not m:
                    continue
                matched = m.group(0)
                try:
                    final = h.callback(matched)
                except Exception:
                    final = matched
                open_label = getattr(h, 'nameopen', 'Open Link')
                copy_label = getattr(h, 'namecopy', 'Copy Address')
                from .translation import _
                return (_(open_label), _(copy_label), str(final))
            except Exception:
                continue
        return None

    def _install_plugin_url_matches(self):
        try:
            from .plugin import PluginRegistry
            reg = PluginRegistry()
            reg.load_plugins(force=True, capabilities_filter={'url_handler'})
            handlers = reg.get_plugins_by_capability('url_handler')
        except Exception:
            handlers = []
        # Add each handler's regex to VTE matchers if possible
        for h in handlers:
            try:
                pattern = getattr(h, 'match', None)
                if not pattern:
                    continue
                try:
                    rx = Vte.Regex.new_for_match(pattern, 0, 0)
                except Exception:
                    rx = None
                if rx is None:
                    continue
                if hasattr(self, 'match_add_regex'):
                    tag = self.match_add_regex(rx, 0)
                elif hasattr(self, 'match_add'):
                    tag = self.match_add(rx, 0)
                else:
                    tag = None
                if tag is not None:
                    try:
                        self._plugin_tag_handlers[int(tag)] = h
                    except Exception:
                        pass
            except Exception:
                continue

    def _on_profile_activate(self, action, param):
        profile = param.get_string() if param else None
        if not profile:
            return
        try:
            if profile in self.config.list_profiles():
                self.config.set_profile(profile, True)
                self.apply_profile()
        except Exception:
            pass

    def _on_selection_changed_actions(self, *args):
        try:
            has_sel = bool(self.get_has_selection()) if hasattr(self, 'get_has_selection') else False
            ag = getattr(self, '_action_group', None)
            if ag is None:
                return
            a_copy = ag.lookup_action('copy')
            a_html = ag.lookup_action('copy_html')
            if a_copy is not None:
                a_copy.set_enabled(has_sel)
            if a_html is not None:
                a_html.set_enabled(has_sel)
        except Exception:
            pass

    def _update_clipboard_actions(self):
        try:
            disp = self.get_display()
            if disp is None:
                return
            paste_ok = True
            paste_sel_ok = True
            try:
                cb = disp.get_clipboard()
                fmts = cb.get_formats() if hasattr(cb, 'get_formats') else None
                if fmts is not None:
                    # Best-effort: require some text-like format
                    ok = False
                    try:
                        # Some backends expose 'text/plain'
                        if hasattr(fmts, 'contain_mime_type') and fmts.contain_mime_type('text/plain'):
                            ok = True
                    except Exception:
                        pass
                    # If we cannot determine, leave enabled
                    paste_ok = ok or True
            except Exception:
                paste_ok = True
            try:
                pcb = disp.get_primary_clipboard()
                fmts2 = pcb.get_formats() if hasattr(pcb, 'get_formats') else None
                if fmts2 is not None:
                    ok2 = False
                    try:
                        if hasattr(fmts2, 'contain_mime_type') and fmts2.contain_mime_type('text/plain'):
                            ok2 = True
                    except Exception:
                        pass
                    paste_sel_ok = ok2 or True
            except Exception:
                paste_sel_ok = True
            ag = getattr(self, '_action_group', None)
            if ag is not None:
                a_paste = ag.lookup_action('paste')
                a_paste_sel = ag.lookup_action('paste_selection')
                if a_paste is not None:
                    a_paste.set_enabled(paste_ok)
                if a_paste_sel is not None:
                    a_paste_sel.set_enabled(paste_sel_ok)
        except Exception:
            pass

    def _on_layout_activate(self, action, param):
        layout = param.get_string() if param else None
        if not layout:
            return
        try:
            win = self.get_root()
            if hasattr(win, 'open_layout_window_by_name'):
                win.open_layout_window_by_name(layout)
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

    def _request_split_auto(self):
        win = self.get_root()
        if hasattr(win, '_on_split_auto'):
            win._on_split_auto()

    def _on_window_title_changed(self, *args):
        # Propagate updated title to window/tab label and titlebar
        title = None
        try:
            title = self.get_window_title()
        except Exception:
            pass
        if not title:
            return
        win = self.get_root()
        if hasattr(win, '_update_title_for_terminal'):
            try:
                win._update_title_for_terminal(self, title)
            except Exception:
                pass

    def _on_bell(self, *args):
        win = self.get_root()
        if hasattr(win, '_notify_bell_for_terminal'):
            try:
                win._notify_bell_for_terminal(self)
            except Exception:
                pass

    # Simple search popover using Vte.Regex if available
    def _show_search_popover(self):
        pop = Gtk.Popover()
        pop.set_parent(self)
        pop.set_has_arrow(True)
        pop.set_autohide(True)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        entry = Gtk.Entry()
        entry.set_placeholder_text(_('Find…'))
        box.append(entry)
        btn_prev = Gtk.Button(label=_('Prev'))
        btn_next = Gtk.Button(label=_('Next'))
        box.append(btn_prev)
        box.append(btn_next)
        # Options: Regex, Case Sensitive
        chk_regex = Gtk.CheckButton(label='.*')
        chk_regex.set_tooltip_text(_('Use regular expressions'))
        try:
            chk_regex.set_active(bool(self._search_is_regex))
        except Exception:
            pass
        box.append(chk_regex)
        chk_case = Gtk.CheckButton(label='Aa')
        chk_case.set_tooltip_text(_('Case sensitive'))
        try:
            from .config import Config as _Cfg
            cfg = _Cfg()
            # Default to global config if no previous state
            chk_case.set_active(bool(self._search_case_sensitive if self._search_case_sensitive is not None else cfg['case_sensitive']))
        except Exception:
            pass
        box.append(chk_case)
        # Whole word, Wrap
        chk_word = Gtk.CheckButton(label='\u2423w')  # visual hint for word
        chk_word.set_tooltip_text(_('Whole word'))
        box.append(chk_word)
        chk_wrap = Gtk.CheckButton(label='\u21ba')  # wrap arrow
        chk_wrap.set_tooltip_text(_('Wrap around'))
        try:
            # Try to reflect current wrap setting if available
            # No direct getter; default to True for convenience
            chk_wrap.set_active(True)
        except Exception:
            pass
        box.append(chk_wrap)
        pop.set_child(box)

        def compile_regex(pattern):
            try:
                from gi.repository import Vte
                # VTE requires multiline compile flag; use inline (?m)
                if chk_case.get_active():
                    rxpat = '(?m)' + pattern
                else:
                    rxpat = '(?im)' + pattern
                rx = Vte.Regex.new_for_search(rxpat, 0, 0)
                return ('vte', rx)
            except Exception:
                try:
                    from gi.repository import GLib
                    # GLib regex: set MULTILINE compile flag; add CASELESS if needed
                    flags = int(getattr(GLib.RegexCompileFlags, 'MULTILINE', 0))
                    if not chk_case.get_active():
                        flags |= int(getattr(GLib.RegexCompileFlags, 'CASELESS', 0))
                    rx = GLib.Regex.new(pattern, flags, 0)
                    return ('glib', rx)
                except Exception:
                    return (None, None)

        def set_search(pattern):
            kind, rx = compile_regex(pattern)
            if not rx:
                return
            flags = 0
            try:
                if kind == 'vte' and hasattr(self, 'search_set_regex'):
                    self.search_set_regex(rx, flags)
                    self._search_last_kind = 'vte'
                elif kind == 'glib' and hasattr(self, 'search_set_gregex'):
                    self.search_set_gregex(rx, flags)
                    self._search_last_kind = 'glib'
                # Wrap around
                if hasattr(self, 'search_set_wrap_around'):
                    self.search_set_wrap_around(bool(chk_wrap.get_active()))
            except Exception:
                pass

        def find_next(forward=True):
            pattern = entry.get_text()
            if not pattern:
                return
            # Compute pattern: regex vs literal
            pat = pattern
            if not chk_regex.get_active():
                try:
                    # Escape literal for regex using Python re
                    import re as _re
                    pat = _re.escape(pattern)
                except Exception:
                    # crude escaping for regex meta
                    for ch in '\\.^$|?*+()[]{}':
                        pat = pat.replace(ch, '\\' + ch)
                # Whole word boundaries
                if chk_word.get_active():
                    pat = r"\b" + pat + r"\b"
            set_search(pat)
            try:
                if forward:
                    self.search_find_next()
                else:
                    self.search_find_previous()
            except Exception:
                pass

        btn_next.connect('clicked', lambda b: find_next(True))
        btn_prev.connect('clicked', lambda b: find_next(False))

        key = Gtk.EventControllerKey()
        from gi.repository import Gdk
        def on_key(_c, keyval, keycode, state):
            if keyval == Gdk.KEY_Return:
                # Shift+Enter searches backwards; allow invert_search preference to flip default
                backward = bool(state & Gdk.ModifierType.SHIFT_MASK)
                try:
                    from .config import Config as _Cfg
                    if bool(_Cfg()['invert_search']):
                        backward = not backward
                except Exception:
                    pass
                find_next(not backward)
                return True
            if keyval == Gdk.KEY_Escape:
                pop.popdown()
                return True
            return False
        key.connect('key-pressed', on_key)
        entry.add_controller(key)
        pop.popup()
        entry.grab_focus()

    def _search_find(self, forward: bool):
        try:
            if forward:
                self.search_find_next()
            else:
                self.search_find_previous()
        except Exception:
            pass

    def _show_group_popover(self):
        # Anchor at terminal titlebar: find unit first child is titlebar
        unit = self.get_parent().get_parent()
        titlebar = unit.get_first_child() if unit is not None else None
        anchor = titlebar if isinstance(titlebar, Gtk.Box) else self
        pop = Gtk.Popover()
        pop.set_parent(anchor)
        pop.set_has_arrow(True)
        pop.set_autohide(True)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        entry = Gtk.Entry()
        entry.set_placeholder_text('Group name…')
        box.append(entry)
        ok = Gtk.Button(label='Create')
        box.append(ok)
        pop.set_child(box)
        def commit():
            name = entry.get_text().strip()
            win = self.get_root()
            if hasattr(win, '_set_unit_group'):
                win._set_unit_group(unit, name or None)
            pop.popdown()
        ok.connect('clicked', lambda b: commit())
        pop.popup()
        entry.grab_focus()

    # Profile application (colors, font, scrollback, cursor)
    def apply_profile(self):
        cfg = self.config
        try:
            prof = cfg.get_profile_by_name(cfg.get_profile())
        except Exception:
            prof = {}

        def rgba(hexstr):
            c = Gdk.RGBA()
            try:
                c.parse(hexstr)
                return c
            except Exception:
                return None

        # Font
        font_str = None
        try:
            if not prof.get('use_system_font', True):
                font_str = prof.get('font')
            else:
                font_str = cfg.get_system_mono_font()
        except Exception:
            font_str = None
        if font_str:
            try:
                desc = Pango.FontDescription(font_str)
                if hasattr(self, 'set_font'):  # API variant
                    self.set_font(desc)
                elif hasattr(self, 'set_font_desc'):
                    self.set_font_desc(desc)
            except Exception:
                pass

        # Colors and palette (respect use_theme_colors)
        try:
            use_theme = bool(prof.get('use_theme_colors', False))
        except Exception:
            use_theme = False
        try:
            if not use_theme:
                fg = rgba(prof.get('foreground_color', ''))
                bg = rgba(prof.get('background_color', ''))
                palette = None
                pal_str = prof.get('palette')
                if pal_str:
                    parts = pal_str.split(':')
                    cols = []
                    for p in parts:
                        rc = rgba(p)
                        if rc:
                            cols.append(rc)
                    if cols:
                        palette = cols
                if hasattr(self, 'set_colors'):
                    # set_colors(fg, bg, palette)
                    self.set_colors(fg, bg, palette)
        except Exception:
            pass

        # Scrollback
        try:
            if prof.get('scrollback_infinite', False):
                self.set_scrollback_lines(-1)
            else:
                self.set_scrollback_lines(int(prof.get('scrollback_lines', 500)))
        except Exception:
            pass

        # Cursor
        try:
            blink = prof.get('cursor_blink', True)
            shape = prof.get('cursor_shape', 'block')
            if hasattr(Vte, 'CursorBlinkMode') and hasattr(self, 'set_cursor_blink_mode'):
                self.set_cursor_blink_mode(Vte.CursorBlinkMode.ON if blink else Vte.CursorBlinkMode.OFF)
            if hasattr(Vte, 'CursorShape') and hasattr(self, 'set_cursor_shape'):
                shp = Vte.CursorShape.BLOCK
                if shape == 'ibeam':
                    shp = Vte.CursorShape.IBEAM
                elif shape == 'underline':
                    shp = Vte.CursorShape.UNDERLINE
                self.set_cursor_shape(shp)
        except Exception:
            pass

        # Bold/bold_is_bright
        try:
            if hasattr(self, 'set_allow_bold'):
                self.set_allow_bold(bool(prof.get('allow_bold', True)))
        except Exception:
            pass
        try:
            if hasattr(self, 'set_bold_is_bright'):
                self.set_bold_is_bright(bool(prof.get('bold_is_bright', False)))
        except Exception:
            pass

        # Cursor colors
        try:
            if not bool(prof.get('cursor_color_default', True)):
                # Determine fg/bg for cursor from profile, with sensible fallbacks
                cur_fg = rgba(prof.get('cursor_fg_color', ''))
                if cur_fg is None:
                    # Fallback to background color
                    cur_fg = rgba(prof.get('background_color', ''))
                cur_bg = rgba(prof.get('cursor_bg_color', ''))
                if cur_bg is None:
                    # Fallback to foreground color
                    cur_bg = rgba(prof.get('foreground_color', ''))
                try:
                    if hasattr(self, 'set_color_cursor_foreground') and cur_fg is not None:
                        self.set_color_cursor_foreground(cur_fg)
                except Exception:
                    pass
                try:
                    if hasattr(self, 'set_color_cursor') and cur_bg is not None:
                        self.set_color_cursor(cur_bg)
                except Exception:
                    pass
            else:
                # Use defaults/theme; if there are reset APIs, attempt best-effort
                pass
        except Exception:
            pass

        # Selection highlight colors
        try:
            if not bool(prof.get('selection_color_default', True)):
                hl_fg = rgba(prof.get('selection_fg_color', ''))
                hl_bg = rgba(prof.get('selection_bg_color', ''))
                try:
                    # Newer VTE
                    if hasattr(self, 'set_color_highlight') and hl_bg is not None:
                        self.set_color_highlight(hl_bg)
                    if hasattr(self, 'set_color_highlight_foreground') and hl_fg is not None:
                        self.set_color_highlight_foreground(hl_fg)
                except Exception:
                    # Some bindings may use set_color_selection
                    try:
                        if hasattr(self, 'set_color_selection') and hl_bg is not None:
                            self.set_color_selection(hl_bg)
                    except Exception:
                        pass
        except Exception:
            pass

        # Copy on selection (connect or disconnect handler per profile)
        try:
            want = bool(prof.get('copy_on_selection', False))
            if want and self._copy_on_sel_handler is None:
                try:
                    self._copy_on_sel_handler = self.connect('selection-changed', self._on_selection_changed_copy)
                except Exception:
                    self._copy_on_sel_handler = None
            if (not want) and self._copy_on_sel_handler is not None:
                try:
                    self.disconnect(self._copy_on_sel_handler)
                except Exception:
                    pass
                self._copy_on_sel_handler = None
        except Exception:
            pass

        # Wheel zoom disable flag
        try:
            self._zoom_wheel_disabled = bool(prof.get('disable_mousewheel_zoom', False))
        except Exception:
            self._zoom_wheel_disabled = False

        # Update stateful profile action so menus reflect the current selection
        try:
            ag = getattr(self, '_action_group', None)
            if ag is not None:
                act = ag.lookup_action('profile')
                if act is not None:
                    from gi.repository import GLib as _GLib
                    act.set_state(_GLib.Variant('s', cfg.get_profile()))
        except Exception:
            pass

    # Scrolling helpers for keybindings
    def scroll_by_line(self, delta_lines: int):
        try:
            self.scroll_lines(int(delta_lines))
        except Exception:
            # Fallback: ignore
            pass

    def scroll_by_page(self, delta_pages: float):
        try:
            rows = 0
            if hasattr(self, 'get_row_count'):
                rows = int(self.get_row_count())
            if rows <= 0:
                rows = 20
            lines = int(round(delta_pages * rows))
            if lines == 0:
                lines = 1 if delta_pages > 0 else -1
            self.scroll_lines(lines)
        except Exception:
            pass

    # Zoom helpers (font scaling)
    def zoom_step(self, delta: float):
        try:
            self._font_scale = max(0.2, min(4.0, self._font_scale + delta))
            if hasattr(self, 'set_font_scale'):
                self.set_font_scale(self._font_scale)
        except Exception:
            pass

    def zoom_reset(self):
        try:
            self._font_scale = 1.0
            if hasattr(self, 'set_font_scale'):
                self.set_font_scale(self._font_scale)
        except Exception:
            pass

    # Copy selection as HTML to clipboard when available
    def copy_selection_as_html(self):
        def _escape_html(s: str) -> str:
            return (
                s.replace('&', '&amp;')
                 .replace('<', '&lt;')
                 .replace('>', '&gt;')
            )

        try:
            # Preferred: direct HTML from VTE if available
            html = None
            plain = None
            if hasattr(self, 'get_text_selected_format'):
                result = self.get_text_selected_format(Vte.Format.HTML)
                if isinstance(result, (list, tuple)) and result and result[0]:
                    html = result[0]
            # Also capture plain text selection
            if hasattr(self, 'get_text_selected'):
                sel = self.get_text_selected()
                if isinstance(sel, (list, tuple)) and sel and sel[0]:
                    plain = sel[0]
            # Fallback: build minimal HTML from selected text or visible screen
            rows = int(getattr(self, 'get_row_count')()) if hasattr(self, 'get_row_count') else 0
            cols = int(getattr(self, 'get_column_count')()) if hasattr(self, 'get_column_count') else 0
            text = plain
            if not text and hasattr(self, 'get_text_range') and rows > 0 and cols > 0:
                rng = self.get_text_range(0, 0, rows - 1, cols - 1)
                if isinstance(rng, (list, tuple)) and rng and rng[0]:
                    text = rng[0]
            if text and not html:
                html = '<pre class="vte-copy">' + _escape_html(text) + '</pre>'
            if html is not None:
                disp = self.get_display()
                if disp is not None:
                    try:
                        # Provide both text/html and text/plain to both clipboard and primary
                        from gi.repository import Gdk, GLib
                        providers = []
                        # HTML variants
                        try:
                            data = GLib.Bytes.new(html.encode('utf-8'))
                            providers.append(Gdk.ContentProvider.new_for_bytes('text/html', data))
                        except Exception:
                            pass
                        try:
                            data2 = GLib.Bytes.new(html.encode('utf-8'))
                            providers.append(Gdk.ContentProvider.new_for_bytes('text/html;charset=utf-8', data2))
                        except Exception:
                            pass
                        # Plain text variants
                        if text:
                            try:
                                providers.append(Gdk.ContentProvider.new_for_bytes('text/plain', GLib.Bytes.new(text.encode('utf-8'))))
                            except Exception:
                                pass
                            try:
                                providers.append(Gdk.ContentProvider.new_for_bytes('text/plain;charset=utf-8', GLib.Bytes.new(text.encode('utf-8'))))
                            except Exception:
                                pass
                        if providers:
                            union = providers[0] if len(providers) == 1 else Gdk.ContentProvider.new_union(providers)
                            # Regular clipboard
                            cb = disp.get_clipboard()
                            cb.set_content(union)
                            # Primary selection, when supported
                            try:
                                prim = disp.get_primary_clipboard()
                                prim.set_content(union)
                            except Exception:
                                pass
                            return
                        # Fallback: set HTML as text
                        cb = disp.get_clipboard()
                        cb.set_text(html)
                        return
                    except Exception:
                        pass
            # As a last resort, fallback to standard copy
            self.copy_clipboard()
        except Exception:
            try:
                self.copy_clipboard()
            except Exception:
                pass
