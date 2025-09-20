"""Minimal GTK4 Vte terminal wrapper."""

import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk, GLib, Vte, Gio, Gdk
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
        # Update window/tab titles on VTE title changes
        try:
            self.connect('window-title-changed', self._on_window_title_changed)
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

        # Change cursor when hovering links while holding Ctrl
        try:
            mctrl = Gtk.EventControllerMotion()
            def on_motion(ctrl, x, y):
                self._update_link_cursor(x, y)
            mctrl.connect('motion', on_motion)
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
                if isinstance(s, str) and (s.startswith('http://') or s.startswith('https://') or s.startswith('ftp://')):
                    return s
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
                else:
                    self.set_cursor(None)
                    try:
                        self.set_tooltip_text(None)
                    except Exception:
                        pass
        except Exception:
            pass

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
            Gio.AppInfo.launch_default_for_uri(url)
        except Exception:
            pass

    # Many GTK3-era plugins expect Terminal.get_vte()
    def get_vte(self):
        return self

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
                        Gio.AppInfo.launch_default_for_uri(url)
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
            act_html.connect('activate', lambda a, p: self.copy_selection_as_html())
            setattr(act_html, '_connected_html', True)

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
        entry.set_placeholder_text('Find…')
        box.append(entry)
        btn_prev = Gtk.Button(label='Prev')
        btn_next = Gtk.Button(label='Next')
        box.append(btn_prev)
        box.append(btn_next)
        # Options: Regex, Case Sensitive
        chk_regex = Gtk.CheckButton(label='.*')
        chk_regex.set_tooltip_text('Use regular expressions')
        try:
            chk_regex.set_active(bool(self._search_is_regex))
        except Exception:
            pass
        box.append(chk_regex)
        chk_case = Gtk.CheckButton(label='Aa')
        chk_case.set_tooltip_text('Case sensitive')
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
        chk_word.set_tooltip_text('Whole word')
        box.append(chk_word)
        chk_wrap = Gtk.CheckButton(label='\u21ba')  # wrap arrow
        chk_wrap.set_tooltip_text('Wrap around')
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
                rxpat = pattern
                # Apply case-insensitive by inline flag when using Vte.Regex
                if not chk_case.get_active():
                    rxpat = '(?i)' + pattern
                rx = Vte.Regex.new_for_search(rxpat, 0, 0)
                return ('vte', rx)
            except Exception:
                try:
                    from gi.repository import GLib
                    flags = 0
                    # Fall back to GLib.Regex; flags for case may differ, so inline handled similarly
                    rxpat = pattern if chk_case.get_active() else '(?i)' + pattern
                    rx = GLib.Regex.new(rxpat, flags, 0)
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

        # Colors and palette
        try:
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
                        try:
                            providers.append(Gdk.ContentProvider.new_for_bytes('text/html', GLib.Bytes.new(html.encode('utf-8'))))
                        except Exception:
                            pass
                        if text:
                            try:
                                providers.append(Gdk.ContentProvider.new_for_bytes('text/plain', GLib.Bytes.new(text.encode('utf-8'))))
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
