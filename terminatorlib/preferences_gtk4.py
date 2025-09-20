"""GTK 4 Preferences window (initial subset).

This dialog provides a minimal set of preferences to unblock the port:
- General: a few global toggles
- Keybindings: edit a handful of common actions (new tab, split horiz/vert, close term)

It updates terminatorlib.config.Config and asks the window to refresh shortcuts.
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from .translation import _

from .config import Config, DEFAULTS
from .plugin import PluginRegistry


class PreferencesWindow(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window | None = None):
        super().__init__(title=_("Preferences"), transient_for=parent, modal=True)
        # Use a smaller default size and allow scrolling inside tabs
        self.set_default_size(640, 440)
        self.config = Config()

        area = self.get_content_area()
        area.set_spacing(12)
        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        area.append(notebook)

        # General tab
        general_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        general_box.set_vexpand(True)
        general_box.set_margin_top(12)
        general_box.set_margin_bottom(12)
        general_box.set_margin_start(12)
        general_box.set_margin_end(12)

        self.chk_always_on_top = Gtk.CheckButton(label=_("Always on top"))
        self.chk_always_on_top.set_active(self.config['always_on_top'])
        general_box.append(self.chk_always_on_top)

        self.chk_hide_taskbar = Gtk.CheckButton(label=_("Hide from taskbar"))
        self.chk_hide_taskbar.set_active(self.config['hide_from_taskbar'])
        general_box.append(self.chk_hide_taskbar)

        self.chk_show_titlebar = Gtk.CheckButton(label=_("Show titlebar above terminals"))
        # Some configs may miss the key; default True
        try:
            self.chk_show_titlebar.set_active(bool(self.config['show_titlebar']))
        except Exception:
            self.chk_show_titlebar.set_active(True)
        general_box.append(self.chk_show_titlebar)

        self.chk_title_bottom = Gtk.CheckButton(label=_("Titlebar below terminal"))
        try:
            self.chk_title_bottom.set_active(bool(self.config['title_at_bottom']))
        except Exception:
            self.chk_title_bottom.set_active(False)
        general_box.append(self.chk_title_bottom)

        # Selection & clipboard behavior
        row_clip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_clear_on_copy = Gtk.CheckButton(label=_("Clear selection after copy"))
        try:
            self.chk_clear_on_copy.set_active(bool(self.config['clear_select_on_copy']))
        except Exception:
            self.chk_clear_on_copy.set_active(False)
        row_clip.append(self.chk_clear_on_copy)
        self.chk_disable_mouse_paste = Gtk.CheckButton(label=_("Disable mouse middle-click paste"))
        try:
            self.chk_disable_mouse_paste.set_active(bool(self.config['disable_mouse_paste']))
        except Exception:
            self.chk_disable_mouse_paste.set_active(False)
        row_clip.append(self.chk_disable_mouse_paste)
        general_box.append(row_clip)

        # Window focus behavior
        row_focus = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_hide_on_lose = Gtk.CheckButton(label=_("Hide window when it loses focus"))
        try:
            self.chk_hide_on_lose.set_active(bool(self.config['hide_on_lose_focus']))
        except Exception:
            self.chk_hide_on_lose.set_active(False)
        row_focus.append(self.chk_hide_on_lose)
        general_box.append(row_focus)

        # Focus mode (click/sloppy)
        row_focusmode = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_focusmode.append(Gtk.Label(label=_("Focus mode"), xalign=0))
        self.combo_focus_mode = Gtk.ComboBoxText()
        self.combo_focus_mode.append_text("click")
        self.combo_focus_mode.append_text("sloppy")
        try:
            current_focus = self.config['focus'] or 'click'
        except Exception:
            current_focus = 'click'
        try:
            idx = 0 if current_focus == 'click' else 1
            self.combo_focus_mode.set_active(idx)
        except Exception:
            self.combo_focus_mode.set_active(0)
        row_focusmode.append(self.combo_focus_mode)
        general_box.append(row_focusmode)

        # Link handling
        row_link = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_link_single = Gtk.CheckButton(label=_("Single-click opens links (with Ctrl)"))
        try:
            self.chk_link_single.set_active(bool(self.config['link_single_click']))
        except Exception:
            self.chk_link_single.set_active(False)
        row_link.append(self.chk_link_single)
        general_box.append(row_link)

        # Custom URL handler
        row_urlh = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_custom_url = Gtk.CheckButton(label=_("Use custom URL handler"))
        try:
            self.chk_custom_url.set_active(bool(self.config['use_custom_url_handler']))
        except Exception:
            self.chk_custom_url.set_active(False)
        row_urlh.append(self.chk_custom_url)
        self.entry_custom_url = Gtk.Entry()
        self.entry_custom_url.set_hexpand(True)
        try:
            self.entry_custom_url.set_text(self.config['custom_url_handler'] or '')
        except Exception:
            pass
        self.entry_custom_url.set_placeholder_text(_("Command, use %s as placeholder"))
        row_urlh.append(self.entry_custom_url)
        general_box.append(row_urlh)

        # Broadcast default
        row_bcast = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_bcast.append(Gtk.Label(label=_("Broadcast default"), xalign=0))
        self.combo_broadcast = Gtk.ComboBoxText()
        for key, label in (("off",_("Off")),("group",_("Group")),("all",_("All"))):
            self.combo_broadcast.append_text(label)
        try:
            curbd = (self.config['broadcast_default'] or 'group').lower()
            idx = {"off":0, "group":1, "all":2}.get(curbd, 1)
            self.combo_broadcast.set_active(idx)
        except Exception:
            self.combo_broadcast.set_active(1)
        row_bcast.append(self.combo_broadcast)
        general_box.append(row_bcast)

        # Tab bar options
        row_tabbar1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_scroll_tabbar = Gtk.CheckButton(label=_("Scrollable tab bar"))
        try:
            self.chk_scroll_tabbar.set_active(self.config['scroll_tabbar'])
        except Exception:
            self.chk_scroll_tabbar.set_active(False)
        row_tabbar1.append(self.chk_scroll_tabbar)
        self.chk_homog_tabbar = Gtk.CheckButton(label=_("Homogeneous tabs"))
        try:
            self.chk_homog_tabbar.set_active(self.config['homogeneous_tabbar'])
        except Exception:
            self.chk_homog_tabbar.set_active(True)
        row_tabbar1.append(self.chk_homog_tabbar)
        general_box.append(row_tabbar1)

        # Tab behavior options
        row_tabbar2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_detachable_tabs = Gtk.CheckButton(label=_("Detachable tabs (drag to new window)"))
        try:
            self.chk_detachable_tabs.set_active(self.config['detachable_tabs'])
        except Exception:
            self.chk_detachable_tabs.set_active(True)
        row_tabbar2.append(self.chk_detachable_tabs)
        self.chk_newtab_after_current = Gtk.CheckButton(label=_("Open new tab after current tab"))
        try:
            self.chk_newtab_after_current.set_active(self.config['new_tab_after_current_tab'])
        except Exception:
            self.chk_newtab_after_current.set_active(False)
        row_tabbar2.append(self.chk_newtab_after_current)
        general_box.append(row_tabbar2)

        # Split behavior
        row_split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_split_with_profile = Gtk.CheckButton(label=_("Always split with current profile"))
        try:
            self.chk_split_with_profile.set_active(self.config['always_split_with_profile'])
        except Exception:
            self.chk_split_with_profile.set_active(False)
        row_split.append(self.chk_split_with_profile)
        general_box.append(row_split)

        # Search options
        row_search = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_case_sensitive = Gtk.CheckButton(label=_("Case sensitive search"))
        try:
            self.chk_case_sensitive.set_active(bool(self.config['case_sensitive']))
        except Exception:
            self.chk_case_sensitive.set_active(True)
        row_search.append(self.chk_case_sensitive)
        self.chk_invert_search = Gtk.CheckButton(label=_("Invert search direction"))
        try:
            self.chk_invert_search.set_active(bool(self.config['invert_search']))
        except Exception:
            self.chk_invert_search.set_active(False)
        row_search.append(self.chk_invert_search)
        general_box.append(row_search)

        row_tabpos = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_tabpos.append(Gtk.Label(label=_("Tab position"), xalign=0))
        self.combo_tabpos = Gtk.ComboBoxText()
        for val in ("top", "bottom", "left", "right"):
            self.combo_tabpos.append_text(val)
        try:
            curpos = (self.config['tab_position'] or 'top').lower()
            self.combo_tabpos.set_active(["top","bottom","left","right"].index(curpos))
        except Exception:
            self.combo_tabpos.set_active(0)
        row_tabpos.append(self.combo_tabpos)
        general_box.append(row_tabpos)

        # Ask before closing
        row_close = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_close.append(Gtk.Label(label=_("Ask before closing"), xalign=0))
        self.ask_combo = Gtk.ComboBoxText()
        for val, label in (("never", "Never"), ("multiple_terminals", "If multiple terminals"), ("always", "Always")):
            self.ask_combo.append_text(label)
        try:
            cur = self.config['ask_before_closing']
        except Exception:
            cur = 'multiple_terminals'
        try:
            idx = {"never":0, "multiple_terminals":1, "always":2}.get(cur, 1)
            self.ask_combo.set_active(idx)
        except Exception:
            self.ask_combo.set_active(1)
        row_close.append(self.ask_combo)
        general_box.append(row_close)

        # Close button on tab
        self.chk_close_btn = Gtk.CheckButton(label=_("Show close button on tab"))
        try:
            self.chk_close_btn.set_active(self.config['close_button_on_tab'])
        except Exception:
            self.chk_close_btn.set_active(True)
        general_box.append(self.chk_close_btn)

        scroller_general = Gtk.ScrolledWindow()
        scroller_general.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller_general.set_child(general_box)
        scroller_general.set_hexpand(True)
        scroller_general.set_vexpand(True)
        notebook.append_page(scroller_general, Gtk.Label(label=_("General")))

        # Keybindings tab
        kb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        kb_box.set_vexpand(True)
        kb_box.set_margin_top(12)
        kb_box.set_margin_bottom(12)
        kb_box.set_margin_start(12)
        kb_box.set_margin_end(12)

        self.kb_entries = {}
        # Use all default keybindings as the editable set
        kb_items = list(DEFAULTS["keybindings"].keys())

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        kb_box.append(grid)

        for i, key in enumerate(kb_items):
            label = key.replace('_', ' ').title()
            grid.attach(Gtk.Label(label=_(label), xalign=0), 0, i, 1, 1)
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            entry = Gtk.Entry()
            entry.set_hexpand(True)
            entry.set_placeholder_text("Press keys…")
            entry.set_text(self.config['keybindings'].get(key, '') or '')
            self._install_accel_capture(entry)
            row_box.append(entry)
            btn_clear = Gtk.Button(label=_("Clear"))
            def make_clear(e):
                return lambda b: e.set_text("")
            btn_clear.connect("clicked", make_clear(entry))
            row_box.append(btn_clear)
            grid.attach(row_box, 1, i, 1, 1)
            self.kb_entries[key] = entry

        scroller_kb = Gtk.ScrolledWindow()
        scroller_kb.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller_kb.set_child(kb_box)
        scroller_kb.set_hexpand(True)
        scroller_kb.set_vexpand(True)
        # Defer appending to enforce original tab order later
        self._pref_page_keybindings = scroller_kb

        # Profiles tab (basic subset)
        prof_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        prof_box.set_vexpand(True)
        prof_box.set_margin_top(12)
        prof_box.set_margin_bottom(12)
        prof_box.set_margin_start(12)
        prof_box.set_margin_end(12)

        # Profile selector
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row1.append(Gtk.Label(label=_("Profile"), xalign=0))
        self.profile_combo = Gtk.ComboBoxText()
        try:
            profiles = sorted(self.config.list_profiles(), key=str.lower)
        except Exception:
            profiles = ['default']
        for p in profiles:
            self.profile_combo.append_text(p)
        try:
            self.profile_combo.set_active(profiles.index(self.config.get_profile()))
        except Exception:
            self.profile_combo.set_active(0)
        row1.append(self.profile_combo)
        prof_box.append(row1)

        # Use system font + font button
        row_font = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_use_system_font = Gtk.CheckButton(label=_("Use system font"))
        try:
            self.chk_use_system_font.set_active(self.config['use_system_font'])
        except Exception:
            self.chk_use_system_font.set_active(True)
        row_font.append(self.chk_use_system_font)
        self.font_btn = Gtk.FontButton()
        try:
            self.font_btn.set_font(self.config['font'])
        except Exception:
            pass
        row_font.append(self.font_btn)
        prof_box.append(row_font)

        # Colors (foreground/background)
        row_colors = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_colors.append(Gtk.Label(label=_("Foreground"), xalign=0))
        self.fg_btn = Gtk.ColorDialogButton()
        try:
            fg = Gdk.RGBA()
            fg.parse(self.config['foreground_color'])
            self.fg_btn.set_rgba(fg)
        except Exception:
            pass
        row_colors.append(self.fg_btn)
        row_colors.append(Gtk.Label(label=_("Background"), xalign=0))
        self.bg_btn = Gtk.ColorDialogButton()
        try:
            bg = Gdk.RGBA()
            bg.parse(self.config['background_color'])
            self.bg_btn.set_rgba(bg)
        except Exception:
            pass
        row_colors.append(self.bg_btn)
        prof_box.append(row_colors)

        # Cursor + bold
        row_cursor = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_cursor_blink = Gtk.CheckButton(label=_("Cursor blink"))
        try:
            self.chk_cursor_blink.set_active(self.config['cursor_blink'])
        except Exception:
            self.chk_cursor_blink.set_active(True)
        row_cursor.append(self.chk_cursor_blink)
        row_cursor.append(Gtk.Label(label=_("Cursor shape")))
        self.cursor_combo = Gtk.ComboBoxText()
        for key in ("block", "ibeam", "underline"):
            self.cursor_combo.append_text(key)
        try:
            curshape = self.config['cursor_shape']
            self.cursor_combo.set_active(["block","ibeam","underline"].index(curshape))
        except Exception:
            self.cursor_combo.set_active(0)
        row_cursor.append(self.cursor_combo)
        self.chk_bold_bright = Gtk.CheckButton(label=_("Bold is bright"))
        try:
            self.chk_bold_bright.set_active(self.config['bold_is_bright'])
        except Exception:
            self.chk_bold_bright.set_active(False)
        row_cursor.append(self.chk_bold_bright)
        prof_box.append(row_cursor)

        # Bell behavior
        bell_frame = Gtk.Frame(label=_("Bell"))
        bell_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_audible_bell = Gtk.CheckButton(label=_("Audible beep"))
        try:
            self.chk_audible_bell.set_active(self.config['audible_bell'])
        except Exception:
            self.chk_audible_bell.set_active(False)
        bell_box.append(self.chk_audible_bell)
        self.chk_icon_bell = Gtk.CheckButton(label=_("Icon bell"))
        try:
            self.chk_icon_bell.set_active(self.config['icon_bell'])
        except Exception:
            self.chk_icon_bell.set_active(True)
        bell_box.append(self.chk_icon_bell)
        self.chk_visible_bell = Gtk.CheckButton(label=_("Visible bell"))
        try:
            self.chk_visible_bell.set_active(self.config['visible_bell'])
        except Exception:
            self.chk_visible_bell.set_active(False)
        bell_box.append(self.chk_visible_bell)
        self.chk_urgent_bell = Gtk.CheckButton(label=_("Window list flash"))
        try:
            self.chk_urgent_bell.set_active(self.config['urgent_bell'])
        except Exception:
            self.chk_urgent_bell.set_active(False)
        bell_box.append(self.chk_urgent_bell)
        bell_frame.set_child(bell_box)
        prof_box.append(bell_frame)

        # Scrolling behavior
        row_scroll_beh = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_scroll_on_key = Gtk.CheckButton(label=_("Scroll on keystroke"))
        try:
            self.chk_scroll_on_key.set_active(self.config['scroll_on_keystroke'])
        except Exception:
            self.chk_scroll_on_key.set_active(True)
        row_scroll_beh.append(self.chk_scroll_on_key)
        self.chk_scroll_on_output = Gtk.CheckButton(label=_("Scroll on output"))
        try:
            self.chk_scroll_on_output.set_active(self.config['scroll_on_output'])
        except Exception:
            self.chk_scroll_on_output.set_active(False)
        row_scroll_beh.append(self.chk_scroll_on_output)
        prof_box.append(row_scroll_beh)

        # Mouse, word chars
        row_mouse = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_mouse_autohide = Gtk.CheckButton(label=_("Mouse autohide"))
        try:
            self.chk_mouse_autohide.set_active(self.config['mouse_autohide'])
        except Exception:
            self.chk_mouse_autohide.set_active(True)
        row_mouse.append(self.chk_mouse_autohide)
        row_mouse.append(Gtk.Label(label=_("Word chars"), xalign=0))
        self.entry_word_chars = Gtk.Entry()
        try:
            self.entry_word_chars.set_text(self.config['word_chars'] or '')
        except Exception:
            pass
        self.entry_word_chars.set_hexpand(True)
        row_mouse.append(self.entry_word_chars)
        prof_box.append(row_mouse)

        # Shell/command behavior
        row_cmd = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_login_shell = Gtk.CheckButton(label=_("Run command as a login shell"))
        try:
            self.chk_login_shell.set_active(self.config['login_shell'])
        except Exception:
            self.chk_login_shell.set_active(False)
        row_cmd.append(self.chk_login_shell)
        self.chk_use_custom_cmd = Gtk.CheckButton(label=_("Use custom command"))
        try:
            self.chk_use_custom_cmd.set_active(self.config['use_custom_command'])
        except Exception:
            self.chk_use_custom_cmd.set_active(False)
        row_cmd.append(self.chk_use_custom_cmd)
        self.entry_custom_cmd = Gtk.Entry()
        self.entry_custom_cmd.set_hexpand(True)
        try:
            self.entry_custom_cmd.set_text(self.config['custom_command'] or '')
        except Exception:
            pass
        self.entry_custom_cmd.set_placeholder_text(_("Command to run"))
        row_cmd.append(self.entry_custom_cmd)
        prof_box.append(row_cmd)
        # Text rendering and theme colors
        row_render = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_allow_bold = Gtk.CheckButton(label=_("Allow bold text"))
        try:
            self.chk_allow_bold.set_active(self.config['allow_bold'])
        except Exception:
            self.chk_allow_bold.set_active(True)
        row_render.append(self.chk_allow_bold)
        self.chk_use_theme_colors = Gtk.CheckButton(label=_("Use theme colors (ignore profile fg/bg/palette)"))
        try:
            self.chk_use_theme_colors.set_active(self.config['use_theme_colors'])
        except Exception:
            self.chk_use_theme_colors.set_active(False)
        row_render.append(self.chk_use_theme_colors)
        prof_box.append(row_render)

        # Cursor colors
        row_cursors = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_cursor_default = Gtk.CheckButton(label=_("Use default cursor colors"))
        try:
            self.chk_cursor_default.set_active(self.config['cursor_color_default'])
        except Exception:
            self.chk_cursor_default.set_active(True)
        row_cursors.append(self.chk_cursor_default)
        row_cursors.append(Gtk.Label(label=_("Cursor FG"), xalign=0))
        self.cursor_fg_btn = Gtk.ColorDialogButton()
        try:
            fg = Gdk.RGBA()
            val = self.config['cursor_fg_color']
            if val:
                fg.parse(val)
                self.cursor_fg_btn.set_rgba(fg)
        except Exception:
            pass
        row_cursors.append(self.cursor_fg_btn)
        row_cursors.append(Gtk.Label(label=_("Cursor BG"), xalign=0))
        self.cursor_bg_btn = Gtk.ColorDialogButton()
        try:
            bg = Gdk.RGBA()
            val = self.config['cursor_bg_color']
            if val:
                bg.parse(val)
                self.cursor_bg_btn.set_rgba(bg)
        except Exception:
            pass
        row_cursors.append(self.cursor_bg_btn)
        # Sensitivity based on default toggle
        def sync_cursor_sensitivity():
            want_default = self.chk_cursor_default.get_active()
            self.cursor_fg_btn.set_sensitive(not want_default)
            self.cursor_bg_btn.set_sensitive(not want_default)
        try:
            self.chk_cursor_default.connect('toggled', lambda *_a: sync_cursor_sensitivity())
        except Exception:
            pass
        sync_cursor_sensitivity()
        prof_box.append(row_cursors)

        # Selection highlight colors
        row_selcols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_selection_default = Gtk.CheckButton(label=_("Use default selection colors"))
        try:
            self.chk_selection_default.set_active(self.config['selection_color_default'])
        except Exception:
            self.chk_selection_default.set_active(True)
        row_selcols.append(self.chk_selection_default)
        row_selcols.append(Gtk.Label(label=_("Selection FG"), xalign=0))
        self.selection_fg_btn = Gtk.ColorDialogButton()
        try:
            v = self.config['selection_fg_color']
            if v:
                col = Gdk.RGBA(); col.parse(v); self.selection_fg_btn.set_rgba(col)
        except Exception:
            pass
        row_selcols.append(self.selection_fg_btn)
        row_selcols.append(Gtk.Label(label=_("Selection BG"), xalign=0))
        self.selection_bg_btn = Gtk.ColorDialogButton()
        try:
            v = self.config['selection_bg_color']
            if v:
                col = Gdk.RGBA(); col.parse(v); self.selection_bg_btn.set_rgba(col)
        except Exception:
            pass
        row_selcols.append(self.selection_bg_btn)
        def sync_selection_sensitivity():
            want_def = self.chk_selection_default.get_active()
            self.selection_fg_btn.set_sensitive(not want_def)
            self.selection_bg_btn.set_sensitive(not want_def)
        try:
            self.chk_selection_default.connect('toggled', lambda *_a: sync_selection_sensitivity())
        except Exception:
            pass
        sync_selection_sensitivity()
        prof_box.append(row_selcols)

        # Zoom behavior (profile)
        row_zoom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_disable_wheel_zoom = Gtk.CheckButton(label=_("Disable Ctrl+Mouse wheel zoom"))
        try:
            self.chk_disable_wheel_zoom.set_active(bool(self.config['disable_mousewheel_zoom']))
        except Exception:
            self.chk_disable_wheel_zoom.set_active(False)
        row_zoom.append(self.chk_disable_wheel_zoom)
        prof_box.append(row_zoom)

        # Selection behavior
        row_sel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_copy_on_select = Gtk.CheckButton(label=_("Copy on selection (profile)"))
        try:
            self.chk_copy_on_select.set_active(bool(self.config['copy_on_selection']))
        except Exception:
            self.chk_copy_on_select.set_active(False)
        row_sel.append(self.chk_copy_on_select)
        prof_box.append(row_sel)

        # Scrollback
        row_scroll = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_scrollback_inf = Gtk.CheckButton(label=_("Infinite scrollback"))
        try:
            self.chk_scrollback_inf.set_active(self.config['scrollback_infinite'])
        except Exception:
            self.chk_scrollback_inf.set_active(False)
        row_scroll.append(self.chk_scrollback_inf)
        row_scroll.append(Gtk.Label(label=_("Lines")))
        adj = Gtk.Adjustment(lower=0, upper=100000, step_increment=100, page_increment=1000)
        self.spin_scrollback = Gtk.SpinButton(adjustment=adj, climb_rate=1.0, digits=0)
        try:
            self.spin_scrollback.set_value(float(self.config['scrollback_lines']))
        except Exception:
            self.spin_scrollback.set_value(500)
        row_scroll.append(self.spin_scrollback)
        prof_box.append(row_scroll)

        # Palette (16 colors)
        pal_frame = Gtk.Frame(label="Palette")
        pal_grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        self.pal_buttons = []
        # Load current palette
        def load_palette():
            try:
                pal_str = self.config['palette']
                parts = pal_str.split(':') if pal_str else []
            except Exception:
                parts = []
            rgba = []
            for i in range(16):
                col = Gdk.RGBA()
                try:
                    col.parse(parts[i])
                except Exception:
                    # sensible defaults
                    col.parse('#000000' if i == 0 else '#ffffff')
                rgba.append(col)
            return rgba
        palette_rgba = load_palette()
        for i in range(16):
            btn = Gtk.ColorDialogButton()
            try:
                btn.set_rgba(palette_rgba[i])
            except Exception:
                pass
            self.pal_buttons.append(btn)
            pal_grid.attach(btn, i % 8, i // 8, 1, 1)
        pal_frame.set_child(pal_grid)
        prof_box.append(pal_frame)

        scroller_prof = Gtk.ScrolledWindow()
        scroller_prof.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller_prof.set_child(prof_box)
        scroller_prof.set_hexpand(True)
        scroller_prof.set_vexpand(True)
        # Defer appending to enforce original tab order later
        self._pref_page_profiles = scroller_prof
        
        # Titlebar styling controls (colors and font)
        title_frame = Gtk.Frame(label=_("Titlebar"))
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        title_box.set_margin_top(8)
        title_box.set_margin_bottom(8)
        title_box.set_margin_start(8)
        title_box.set_margin_end(8)
        # Font controls
        row_tfont = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_title_use_system_font = Gtk.CheckButton(label=_("Use system font for titlebar"))
        try:
            self.chk_title_use_system_font.set_active(self.config['title_use_system_font'])
        except Exception:
            self.chk_title_use_system_font.set_active(True)
        row_tfont.append(self.chk_title_use_system_font)
        self.title_font_btn = Gtk.FontButton()
        try:
            self.title_font_btn.set_font(self.config['title_font'])
        except Exception:
            pass
        row_tfont.append(self.title_font_btn)
        title_box.append(row_tfont)
        # Colors for TX/RX/Inactive (fg/bg)
        def add_color_row(label_text, key_fg, key_bg):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.append(Gtk.Label(label=label_text, xalign=0))
            fg_btn = Gtk.ColorDialogButton()
            try:
                v = self.config[key_fg]
                if v:
                    col = Gdk.RGBA(); col.parse(v); fg_btn.set_rgba(col)
            except Exception:
                pass
            row.append(fg_btn)
            bg_btn = Gtk.ColorDialogButton()
            try:
                v = self.config[key_bg]
                if v:
                    col = Gdk.RGBA(); col.parse(v); bg_btn.set_rgba(col)
            except Exception:
                pass
            row.append(bg_btn)
            return row, fg_btn, bg_btn
        row_tx, self.tx_fg_btn, self.tx_bg_btn = add_color_row(_("Transmit (TX) fg/bg"), 'title_transmit_fg_color', 'title_transmit_bg_color')
        row_rx, self.rx_fg_btn, self.rx_bg_btn = add_color_row(_("Receive (RX) fg/bg"), 'title_receive_fg_color', 'title_receive_bg_color')
        row_in, self.in_fg_btn, self.in_bg_btn = add_color_row(_("Inactive fg/bg"), 'title_inactive_fg_color', 'title_inactive_bg_color')
        title_box.append(row_tx)
        title_box.append(row_rx)
        title_box.append(row_in)
        title_frame.set_child(title_box)
        prof_box.append(title_frame)

        # Layouts tab (basic editor)
        layouts_root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        layouts_root.set_margin_top(12)
        layouts_root.set_margin_bottom(12)
        layouts_root.set_margin_start(12)
        layouts_root.set_margin_end(12)

        # Left: Layouts list + controls (add/rename/remove)
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_box.set_hexpand(True)
        left_box.set_vexpand(True)
        self.layouts_list = Gtk.ListBox()
        self.layouts_list.set_hexpand(True)
        self.layouts_list.set_vexpand(True)
        self.layouts_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        left_box.append(self.layouts_list)
        # Controls row (match original: Add, Refresh, Remove)
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_add_layout = Gtk.Button(label=_("Add layout…"))
        btn_refresh_from_current = Gtk.Button(label=_("Refresh from current"))
        btn_remove_layout = Gtk.Button(label=_("Remove layout"))
        # Keep references for sensitivity updates based on selection
        self.btn_remove_layout = btn_remove_layout
        btn_row.append(btn_add_layout)
        btn_row.append(btn_refresh_from_current)
        btn_row.append(btn_remove_layout)
        left_box.append(btn_row)

        def on_remove_layout(_b):
            row = self.layouts_list.get_selected_row()
            if not row:
                return
            name = getattr(row, '_name', None)
            if not name or name == 'default':
                return
            try:
                self.config.del_layout(name)
                self.config.save()
                _refresh_layouts_list()
            except Exception:
                pass
        btn_remove_layout.connect('clicked', on_remove_layout)
        
        def _get_parent_window():
            parent = self.get_transient_for()
            return parent if parent is not None else None

        # Add layout uses current window description (original behavior)
        def on_add_layout(_b):
            win = _get_parent_window()
            if win is None or not hasattr(win, 'describe_layout'):
                self._message(_("This action requires a running GTK4 window."))
                return
            dlg = Gtk.Dialog(title=_("Add Layout from Current Window"), transient_for=self, modal=True)
            box = dlg.get_content_area(); box.set_spacing(8)
            entry = Gtk.Entry(); entry.set_placeholder_text(_("Layout name")); box.append(entry)
            dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
            dlg.add_button(_("Add"), Gtk.ResponseType.OK)
            dlg.show()
            def on_resp(d, resp):
                if resp == Gtk.ResponseType.OK:
                    name = entry.get_text().strip()
                    if name:
                        try:
                            current_layout = win.describe_layout(save_cwd=True)
                            if self.config.add_layout(name, current_layout):
                                self.config.save()
                                _refresh_layouts_list()
                                # Select the new layout
                                r = self.layouts_list.get_first_child()
                                while r is not None:
                                    if getattr(r, '_name', None) == name:
                                        self.layouts_list.select_row(r)
                                        break
                                    r = r.get_next_sibling()
                        except Exception:
                            pass
                d.destroy()
            dlg.connect('response', on_resp)
            dlg.present()
        btn_add_layout.connect('clicked', on_add_layout)

        def on_refresh_from_current(_b):
            win = _get_parent_window()
            if win is None or not hasattr(win, 'describe_layout'):
                self._message(_("This action requires a running GTK4 window."))
                return
            row = self.layouts_list.get_selected_row()
            if not row:
                return
            name = getattr(row, '_name', None)
            if not name:
                return
            try:
                current_layout = win.describe_layout(save_cwd=True)
                config_layout = self.config.base.get_layout(name)
                # Copy terminal-specific fields from the config layout into the new layout by matching UUIDs
                for key in ('directory', 'command', 'profile'):
                    try:
                        self.config.copy_layout_item(config_layout, current_layout, key)
                    except Exception:
                        pass
                if self.config.replace_layout(name, current_layout):
                    self.config.save()
                    _refresh_layouts_list()
                    # Reselect
                    r = self.layouts_list.get_first_child()
                    while r is not None:
                        if getattr(r, '_name', None) == name:
                            self.layouts_list.select_row(r)
                            break
                        r = r.get_next_sibling()
            except Exception:
                pass
        btn_refresh_from_current.connect('clicked', on_refresh_from_current)
        layouts_root.append(left_box)

        # Right: items list and editor
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_box.set_hexpand(True)
        right_box.set_vexpand(True)
        self.layout_items = Gtk.ListBox()
        self.layout_items.set_hexpand(True)
        self.layout_items.set_vexpand(True)
        self.layout_items.set_selection_mode(Gtk.SelectionMode.SINGLE)
        right_box.append(self.layout_items)
        editor = Gtk.Grid(column_spacing=8, row_spacing=6)
        r = 0
        editor.attach(Gtk.Label(label=_("Profile"), xalign=0), 0, r, 1, 1)
        self.layout_item_profile = Gtk.ComboBoxText(); r += 1
        editor.attach(self.layout_item_profile, 1, r-1, 1, 1)
        editor.attach(Gtk.Label(label=_("Command"), xalign=0), 0, r, 1, 1)
        self.layout_item_command = Gtk.Entry(); self.layout_item_command.set_hexpand(True); r += 1
        editor.attach(self.layout_item_command, 1, r-1, 1, 1)
        editor.attach(Gtk.Label(label=_("Working directory"), xalign=0), 0, r, 1, 1)
        self.layout_item_workdir = Gtk.Entry(); self.layout_item_workdir.set_hexpand(True); r += 1
        editor.attach(self.layout_item_workdir, 1, r-1, 1, 1)
        right_box.append(editor)
        layouts_root.append(right_box)

        scroller_layouts = Gtk.ScrolledWindow()
        scroller_layouts.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller_layouts.set_child(layouts_root)
        scroller_layouts.set_hexpand(True)
        scroller_layouts.set_vexpand(True)
        # Defer append to control tab order
        self._pref_page_layouts = scroller_layouts

        # State and handlers for layouts editor
        self._current_layout = None
        self._current_layout_item = None
        def _set_layout_buttons_sensitivity(selected_name: str | None):
            try:
                # Match GTK3: disable only the Remove button for default layout
                self.btn_remove_layout.set_sensitive(bool(selected_name and selected_name != 'default'))
            except Exception:
                pass

        def _refresh_layouts_list():
            # Populate layouts list with default first
            while (row := self.layouts_list.get_first_child()) is not None:
                self.layouts_list.remove(row)
            names = []
            try:
                names = sorted(self.config.list_layouts(), key=str.lower)
            except Exception:
                names = []
            if 'default' in names:
                names.remove('default'); names = ['default'] + names
            for nm in names:
                row = Gtk.ListBoxRow()
                lb = Gtk.Label(label=nm, xalign=0); lb.set_hexpand(True)
                row.set_child(lb); row._name = nm
                self.layouts_list.append(row)
            # Select first
            if names:
                first_row = self.layouts_list.get_row_at_index(0)
                self.layouts_list.select_row(first_row)
                try:
                    _set_layout_buttons_sensitivity(getattr(first_row, '_name', None))
                except Exception:
                    pass
        def _refresh_items_for_layout(name):
            self._current_layout = name
            while (row := self.layout_items.get_first_child()) is not None:
                self.layout_items.remove(row)
            layout = {}
            try:
                layout = self.config.layout_get_config(name)
            except Exception:
                layout = {}
            # List only Terminal items; show key as display
            for key, section in layout.items():
                try:
                    if section.get('type') != 'Terminal':
                        continue
                    row = Gtk.ListBoxRow(); row._item = key
                    lb = Gtk.Label(label=key, xalign=0); lb.set_hexpand(True)
                    row.set_child(lb)
                    self.layout_items.append(row)
                except Exception:
                    continue
            # Select first
            first = self.layout_items.get_row_at_index(0)
            if first: self.layout_items.select_row(first)
        def _refresh_profiles_combo():
            self.layout_item_profile.remove_all()
            names = []
            try:
                names = sorted(self.config.list_profiles(), key=str.lower)
            except Exception:
                names = ['default']
            for nm in names:
                self.layout_item_profile.append_text(nm)
        def _load_item_editor(item):
            self._current_layout_item = item
            if not self._current_layout or not item:
                return
            try:
                layout = self.config.layout_get_config(self._current_layout)
                section = layout.get(item, {})
            except Exception:
                section = {}
            # Profile
            _refresh_profiles_combo()
            try:
                prof = section.get('profile') or 'default'
                # find index
                idx = 0
                model = self.layout_item_profile
                # ComboBoxText has limited API; iterate children by text
                allp = sorted(self.config.list_profiles(), key=str.lower)
                if prof in allp:
                    idx = allp.index(prof)
                self.layout_item_profile.set_active(idx)
            except Exception:
                self.layout_item_profile.set_active(0)
            # Command
            try:
                self.layout_item_command.set_text(section.get('command') or '')
            except Exception:
                self.layout_item_command.set_text('')
            # Workdir
            try:
                self.layout_item_workdir.set_text(section.get('directory') or '')
            except Exception:
                self.layout_item_workdir.set_text('')
        def _save_item_editor():
            if not self._current_layout or not self._current_layout_item:
                return
            try:
                layout = self.config.layout_get_config(self._current_layout)
                section = layout.get(self._current_layout_item, {})
                section['profile'] = self.layout_item_profile.get_active_text() or ''
                section['command'] = self.layout_item_command.get_text() or ''
                section['directory'] = self.layout_item_workdir.get_text() or ''
                layout[self._current_layout_item] = section
                self.config.layout_set_config(self._current_layout, layout)
                self.config.save()
            except Exception:
                pass
        # Selections
        def on_layout_selected(_lb, row):
            name = getattr(row, '_name', None) if row else None
            if name:
                _refresh_items_for_layout(name)
            _set_layout_buttons_sensitivity(name)
        def on_item_selected(_lb, row):
            item = getattr(row, '_item', None) if row else None
            _load_item_editor(item)
        self.layouts_list.connect('row-selected', on_layout_selected)
        self.layout_items.connect('row-selected', on_item_selected)
        # Save on edits
        self.layout_item_profile.connect('changed', lambda *_a: _save_item_editor())
        self.layout_item_command.connect('activate', lambda *_a: _save_item_editor())
        self.layout_item_workdir.connect('activate', lambda *_a: _save_item_editor())
        # Populate initial list
        _refresh_layouts_list()

        # Plugins tab (enable/disable) grouped by capability
        plugins_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        plugins_box.set_vexpand(True)
        plugins_box.set_margin_top(12)
        plugins_box.set_margin_bottom(12)
        plugins_box.set_margin_start(12)
        plugins_box.set_margin_end(12)

        self.plugin_checks = {}
        enabled = set(self.config['enabled_plugins'] or [])
        try:
            registry = PluginRegistry()
            registry.load_plugins(force=True)
            by_cap = { 'terminal_menu': [], 'url_handler': [], 'other': [] }
            for name, cls in getattr(registry, 'available_plugins', {}).items():
                try:
                    caps = set(getattr(cls, 'capabilities', []) or [])
                except Exception:
                    caps = set()
                if 'terminal_menu' in caps:
                    by_cap['terminal_menu'].append(name)
                elif 'url_handler' in caps:
                    by_cap['url_handler'].append(name)
                else:
                    by_cap['other'].append(name)
        except Exception:
            by_cap = { 'terminal_menu': [], 'url_handler': [], 'other': [] }

        def add_plugin_section(title, names):
            if not names:
                return
            frame = Gtk.Frame(label=title)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            frame.set_child(box)
            for name in sorted(names):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                # Plugin class names are not translated
                chk = Gtk.CheckButton(label=name)
                chk.set_active(name in enabled)
                row.append(chk)
                box.append(row)
                self.plugin_checks[name] = chk
            plugins_box.append(frame)

        add_plugin_section(_("Terminal Menu Plugins"), by_cap.get('terminal_menu'))
        add_plugin_section(_("URL Handler Plugins"), by_cap.get('url_handler'))
        add_plugin_section(_("Other Plugins"), by_cap.get('other'))

        # URL handler patterns (read-only summary)
        try:
            if by_cap.get('url_handler'):
                frame = Gtk.Frame(label=_("URL Handler Patterns"))
                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                frame.set_child(vbox)
                for name in sorted(by_cap.get('url_handler')):
                    try:
                        cls = registry.available_plugins.get(name)
                        pattern = getattr(cls, 'match', '')
                    except Exception:
                        pattern = ''
                    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                    row.append(Gtk.Label(label=name, xalign=0))
                    pat_entry = Gtk.Entry()
                    pat_entry.set_hexpand(True)
                    try:
                        pat_entry.set_text(pattern or '')
                    except Exception:
                        pass
                    pat_entry.set_editable(False)
                    row.append(pat_entry)
                    vbox.append(row)
                plugins_box.append(frame)
        except Exception:
            pass

        scroller_plugins = Gtk.ScrolledWindow()
        scroller_plugins.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller_plugins.set_child(plugins_box)
        scroller_plugins.set_hexpand(True)
        scroller_plugins.set_vexpand(True)
        # Defer appending to enforce original tab order later
        self._pref_page_plugins = scroller_plugins

        # Buttons
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.add_button(_("Save"), Gtk.ResponseType.OK)
        self.connect("response", self.on_response)

        # Profile management actions (buttons under profile selector)
        try:
            pm_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            btn_add = Gtk.Button(label=_("Add…"))
            btn_ren = Gtk.Button(label=_("Rename…"))
            btn_del = Gtk.Button(label=_("Delete"))
            pm_row.append(btn_add)
            pm_row.append(btn_ren)
            pm_row.append(btn_del)
            prof_box.append(pm_row)
            btn_add.connect('clicked', lambda b: self._on_profile_add())
            btn_ren.connect('clicked', lambda b: self._on_profile_rename())
            btn_del.connect('clicked', lambda b: self._on_profile_delete())
        except Exception:
            pass

        # Enforce original tab order: General, Profiles, Layouts, Keybindings, Plugins
        try:
            # General already appended
            if hasattr(self, '_pref_page_profiles'):
                notebook.append_page(self._pref_page_profiles, Gtk.Label(label=_("Profiles")))
            if hasattr(self, '_pref_page_layouts'):
                notebook.append_page(self._pref_page_layouts, Gtk.Label(label=_("Layouts")))
            if hasattr(self, '_pref_page_keybindings'):
                notebook.append_page(self._pref_page_keybindings, Gtk.Label(label=_("Keybindings")))
            if hasattr(self, '_pref_page_plugins'):
                notebook.append_page(self._pref_page_plugins, Gtk.Label(label=_("Plugins")))
        except Exception:
            pass

    def _install_accel_capture(self, entry: Gtk.Entry):
        ctrl = Gtk.EventControllerKey()

        def on_key(controller, keyval, keycode, state):
            # Filter modifier-only presses using GTK4 mask names
            allowed = 0
            for name in ('SHIFT_MASK', 'CONTROL_MASK', 'ALT_MASK', 'SUPER_MASK', 'META_MASK'):
                try:
                    allowed |= int(getattr(Gdk.ModifierType, name))
                except Exception:
                    pass
            mods = state & allowed
            # Use Gtk.accelerator_name to build canonical string
            accel = Gtk.accelerator_name(keyval, mods)
            # Avoid None when only modifiers are pressed
            if accel:
                entry.set_text(accel)
            return True

        ctrl.connect("key-pressed", on_key)
        entry.add_controller(ctrl)

    def on_response(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            self.destroy()
            return
        # 1) Save general/global options
        try:
            self.config['always_on_top'] = self.chk_always_on_top.get_active()
            self.config['hide_from_taskbar'] = self.chk_hide_taskbar.get_active()
            self.config['show_titlebar'] = self.chk_show_titlebar.get_active()
            self.config['title_at_bottom'] = self.chk_title_bottom.get_active()
            self.config['scroll_tabbar'] = self.chk_scroll_tabbar.get_active()
            self.config['homogeneous_tabbar'] = self.chk_homog_tabbar.get_active()
            self.config['detachable_tabs'] = self.chk_detachable_tabs.get_active()
            self.config['new_tab_after_current_tab'] = self.chk_newtab_after_current.get_active()
            self.config['always_split_with_profile'] = self.chk_split_with_profile.get_active()
            self.config['clear_select_on_copy'] = self.chk_clear_on_copy.get_active()
            self.config['disable_mouse_paste'] = self.chk_disable_mouse_paste.get_active()
            self.config['hide_on_lose_focus'] = self.chk_hide_on_lose.get_active()
            self.config['tab_position'] = self.combo_tabpos.get_active_text() or 'top'
            # Search defaults
            self.config['case_sensitive'] = self.chk_case_sensitive.get_active()
            self.config['invert_search'] = self.chk_invert_search.get_active()
            # Link handling
            self.config['link_single_click'] = self.chk_link_single.get_active()
            # Custom URL handler
            try:
                self.config['use_custom_url_handler'] = self.chk_custom_url.get_active()
                self.config['custom_url_handler'] = self.entry_custom_url.get_text()
            except Exception:
                pass
            # Focus mode
            try:
                mode = self.combo_focus_mode.get_active_text() or 'click'
                self.config['focus'] = 'sloppy' if mode == 'sloppy' else 'click'
            except Exception:
                pass
            # Broadcast default
            bd_idx = self.combo_broadcast.get_active()
            self.config['broadcast_default'] = {0:'off',1:'group',2:'all'}.get(bd_idx, 'group')
            # Ask before closing
            idx = self.ask_combo.get_active()
            self.config['ask_before_closing'] = {0:'never',1:'multiple_terminals',2:'always'}.get(idx, 'multiple_terminals')
            # Close button on tab
            self.config['close_button_on_tab'] = self.chk_close_btn.get_active()
        except Exception:
            pass

        # 2) Save plugin enable/disable
        try:
            enabled = [name for name, chk in self.plugin_checks.items() if chk.get_active()]
            self.config['enabled_plugins'] = enabled
            # Optionally refresh plugin registry
            reg = PluginRegistry()
            reg.load_plugins(force=True)
        except Exception:
            pass

        # 3) Save selected profile settings
        try:
            profile = self.profile_combo.get_active_text() or self.config.get_profile()
            # Temporarily switch profile to write keys
            self.config.set_profile(profile, True)
            self.config['use_system_font'] = self.chk_use_system_font.get_active()
            try:
                font = self.font_btn.get_font()
                if font:
                    self.config['font'] = font
            except Exception:
                pass
            def rgba_to_hex(rgba: Gdk.RGBA):
                r = int(round(rgba.red * 255))
                g = int(round(rgba.green * 255))
                b = int(round(rgba.blue * 255))
                return f"#{r:02x}{g:02x}{b:02x}"
            try:
                self.config['foreground_color'] = rgba_to_hex(self.fg_btn.get_rgba())
                self.config['background_color'] = rgba_to_hex(self.bg_btn.get_rgba())
            except Exception:
                pass
            self.config['cursor_blink'] = self.chk_cursor_blink.get_active()
            self.config['cursor_shape'] = self.cursor_combo.get_active_text() or 'block'
            self.config['bold_is_bright'] = self.chk_bold_bright.get_active()
            try:
                self.config['allow_bold'] = self.chk_allow_bold.get_active()
            except Exception:
                pass
            try:
                self.config['use_theme_colors'] = self.chk_use_theme_colors.get_active()
            except Exception:
                pass
            try:
                self.config['disable_mousewheel_zoom'] = self.chk_disable_wheel_zoom.get_active()
            except Exception:
                pass
            # Bells
            try:
                self.config['audible_bell'] = self.chk_audible_bell.get_active()
                self.config['visible_bell'] = self.chk_visible_bell.get_active()
                self.config['urgent_bell'] = self.chk_urgent_bell.get_active()
                self.config['icon_bell'] = self.chk_icon_bell.get_active()
            except Exception:
                pass
            # Scroll behavior
            try:
                self.config['scroll_on_keystroke'] = self.chk_scroll_on_key.get_active()
                self.config['scroll_on_output'] = self.chk_scroll_on_output.get_active()
            except Exception:
                pass
            # Mouse/word chars
            try:
                self.config['mouse_autohide'] = self.chk_mouse_autohide.get_active()
                self.config['word_chars'] = self.entry_word_chars.get_text()
            except Exception:
                pass
            # Command behavior
            try:
                self.config['login_shell'] = self.chk_login_shell.get_active()
                self.config['use_custom_command'] = self.chk_use_custom_cmd.get_active()
                self.config['custom_command'] = self.entry_custom_cmd.get_text()
            except Exception:
                pass
            # Cursor colors
            try:
                self.config['cursor_color_default'] = self.chk_cursor_default.get_active()
                # Only store fg/bg when not default
                if not self.chk_cursor_default.get_active():
                    def rgba_to_hex(rgba: Gdk.RGBA):
                        r = int(round(rgba.red * 255))
                        g = int(round(rgba.green * 255))
                        b = int(round(rgba.blue * 255))
                        return f"#{r:02x}{g:02x}{b:02x}"
                    self.config['cursor_fg_color'] = rgba_to_hex(self.cursor_fg_btn.get_rgba())
                    self.config['cursor_bg_color'] = rgba_to_hex(self.cursor_bg_btn.get_rgba())
            except Exception:
                pass
            # Titlebar colors and font
            try:
                def rgba_to_hex(rgba: Gdk.RGBA):
                    r = int(round(rgba.red * 255))
                    g = int(round(rgba.green * 255))
                    b = int(round(rgba.blue * 255))
                    return f"#{r:02x}{g:02x}{b:02x}"
                self.config['title_use_system_font'] = self.chk_title_use_system_font.get_active()
                try:
                    f = self.title_font_btn.get_font()
                    if f:
                        self.config['title_font'] = f
                except Exception:
                    pass
                self.config['title_transmit_fg_color'] = rgba_to_hex(self.tx_fg_btn.get_rgba())
                self.config['title_transmit_bg_color'] = rgba_to_hex(self.tx_bg_btn.get_rgba())
                self.config['title_receive_fg_color']  = rgba_to_hex(self.rx_fg_btn.get_rgba())
                self.config['title_receive_bg_color']  = rgba_to_hex(self.rx_bg_btn.get_rgba())
                self.config['title_inactive_fg_color'] = rgba_to_hex(self.in_fg_btn.get_rgba())
                self.config['title_inactive_bg_color'] = rgba_to_hex(self.in_bg_btn.get_rgba())
            except Exception:
                pass
            # Selection highlight colors
            try:
                self.config['selection_color_default'] = self.chk_selection_default.get_active()
                if not self.chk_selection_default.get_active():
                    def rgba_to_hex(rgba: Gdk.RGBA):
                        r = int(round(rgba.red * 255))
                        g = int(round(rgba.green * 255))
                        b = int(round(rgba.blue * 255))
                        return f"#{r:02x}{g:02x}{b:02x}"
                    self.config['selection_fg_color'] = rgba_to_hex(self.selection_fg_btn.get_rgba())
                    self.config['selection_bg_color'] = rgba_to_hex(self.selection_bg_btn.get_rgba())
            except Exception:
                pass
            self.config['scrollback_infinite'] = self.chk_scrollback_inf.get_active()
            try:
                self.config['scrollback_lines'] = int(self.spin_scrollback.get_value())
            except Exception:
                pass
            # Selection behavior (profile)
            try:
                self.config['copy_on_selection'] = self.chk_copy_on_select.get_active()
            except Exception:
                pass
            # Palette writeback
            try:
                cols = [rgba_to_hex(btn.get_rgba()) for btn in self.pal_buttons]
                self.config['palette'] = ':'.join(cols)
            except Exception:
                pass
        except Exception:
            pass

        # 4) Save keybindings (with duplicate detection)
        kb = self.config['keybindings']
        values = {}
        for key, entry in self.kb_entries.items():
            accel = entry.get_text().strip()
            if accel:
                kv, mods = Gtk.accelerator_parse(accel)
                accel = Gtk.accelerator_name(kv, mods) if kv != 0 else accel
            if accel:
                if accel in values:
                    self._show_duplicate_dialog(accel, values[accel], key)
                    return
                values[accel] = key
            kb[key] = accel

        # Persist all changes once
        try:
            self.config.save()
        except Exception:
            pass

        # 5) Ask parent to refresh live UI where applicable
        parent = self.get_transient_for()
        if parent:
            if hasattr(parent, 'refresh_shortcuts'):
                parent.refresh_shortcuts()
            if hasattr(parent, 'refresh_titlebars'):
                parent.refresh_titlebars(self.chk_show_titlebar.get_active())
            if hasattr(parent, 'refresh_titlebar_position'):
                parent.refresh_titlebar_position(self.chk_title_bottom.get_active())
            if hasattr(parent, 'refresh_notebook_prefs'):
                parent.refresh_notebook_prefs()
            if hasattr(parent, 'refresh_tab_close_buttons'):
                parent.refresh_tab_close_buttons()
            if hasattr(parent, 'refresh_window_hints'):
                parent.refresh_window_hints(self.chk_always_on_top.get_active(), self.chk_hide_taskbar.get_active())
            # Apply broadcast default immediately
            if hasattr(parent, '_set_groupsend'):
                try:
                    bd = {0:'off',1:'group',2:'all'}.get(self.combo_broadcast.get_active(), 'group')
                    parent._set_groupsend(bd)
                except Exception:
                    pass
            # Apply titlebar styling (colors and font)
            if hasattr(parent, 'refresh_titlebar_style'):
                parent.refresh_titlebar_style()
            # Apply updated profile to focused terminal when relevant
            try:
                term = parent._get_focused_terminal()
                if term is not None and hasattr(term, 'config') and hasattr(term, 'apply_profile'):
                    sel_profile = self.profile_combo.get_active_text() or term.config.get_profile()
                    if term.config.get_profile() == sel_profile:
                        term.apply_profile()
            except Exception:
                pass

        self.destroy()

    def _on_profile_add(self):
        dlg = Gtk.Dialog(title=_("Add Profile"), transient_for=self, modal=True)
        box = dlg.get_content_area()
        entry = Gtk.Entry()
        entry.set_placeholder_text("Profile name")
        box.append(entry)
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_("Add"), Gtk.ResponseType.OK)
        dlg.show()
        def on_resp(d, resp):
            if resp == Gtk.ResponseType.OK:
                name = entry.get_text().strip()
                if name and name not in self.config.list_profiles():
                    try:
                        self.config.add_profile(name, self.config.get_profile())
                        # Update combo
                        self.profile_combo.append_text(name)
                    except Exception:
                        pass
            d.destroy()
        dlg.connect('response', on_resp)
        dlg.present()

    def _on_profile_rename(self):
        current = self.profile_combo.get_active_text() or self.config.get_profile()
        if not current or current == 'default':
            self._message("Cannot rename this profile")
            return
        dlg = Gtk.Dialog(title=_("Rename Profile"), transient_for=self, modal=True)
        box = dlg.get_content_area()
        entry = Gtk.Entry()
        entry.set_text(current)
        box.append(entry)
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_("Rename"), Gtk.ResponseType.OK)
        dlg.show()
        def on_resp(d, resp):
            if resp == Gtk.ResponseType.OK:
                new = entry.get_text().strip()
                if new and new != current:
                    try:
                        self.config.rename_profile(current, new)
                        # Refill combo
                        self.profile_combo.remove_all()
                        for p in sorted(self.config.list_profiles(), key=str.lower):
                            self.profile_combo.append_text(p)
                        # Switch to new profile
                        self.config.set_profile(new, True)
                        try:
                            idx = sorted(self.config.list_profiles(), key=str.lower).index(new)
                            self.profile_combo.set_active(idx)
                        except Exception:
                            pass
                    except Exception:
                        pass
            d.destroy()
        dlg.connect('response', on_resp)
        dlg.present()

    def _on_profile_delete(self):
        current = self.profile_combo.get_active_text() or self.config.get_profile()
        if not current or current == 'default':
            self._message("Cannot delete this profile")
            return
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.NONE,
                                text=f"Delete profile '{current}'?")
        dlg.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_("Delete"), Gtk.ResponseType.OK)
        def on_resp(d, resp):
            if resp == Gtk.ResponseType.OK:
                try:
                    self.config.del_profile(current)
                    # Rebuild combo
                    self.profile_combo.remove_all()
                    plist = sorted(self.config.list_profiles(), key=str.lower)
                    for p in plist:
                        self.profile_combo.append_text(p)
                    try:
                        idx = plist.index(self.config.get_profile())
                        self.profile_combo.set_active(idx)
                    except Exception:
                        self.profile_combo.set_active(0)
                except Exception:
                    pass
            d.destroy()
        dlg.connect('response', on_resp)
        dlg.present()

    def _message(self, text: str):
        msg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.INFO,
                                buttons=Gtk.ButtonsType.OK,
                                text=text)
        msg.connect('response', lambda d, r: d.destroy())
        msg.present()

    def _show_duplicate_dialog(self, accel, first_key, second_key):
        msg = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=f"Duplicate shortcut: {accel}",
        )
        msg.format_secondary_text(
            f"The accelerator {accel} is already used by '{first_key}'. "
            f"Cannot assign it to '{second_key}'."
        )
        def on_resp(dlg, resp):
            dlg.destroy()
        msg.connect("response", on_resp)
        msg.present()
