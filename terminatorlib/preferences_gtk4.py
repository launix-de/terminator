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
        super().__init__(title="Preferences", transient_for=parent, modal=True)
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
        general_box.set_margin_top(12)
        general_box.set_margin_bottom(12)
        general_box.set_margin_start(12)
        general_box.set_margin_end(12)

        self.chk_always_on_top = Gtk.CheckButton(label="Always on top")
        self.chk_always_on_top.set_active(self.config['always_on_top'])
        general_box.append(self.chk_always_on_top)

        self.chk_hide_taskbar = Gtk.CheckButton(label="Hide from taskbar")
        self.chk_hide_taskbar.set_active(self.config['hide_from_taskbar'])
        general_box.append(self.chk_hide_taskbar)

        self.chk_show_titlebar = Gtk.CheckButton(label="Show titlebar above terminals")
        # Some configs may miss the key; default True
        try:
            self.chk_show_titlebar.set_active(bool(self.config['show_titlebar']))
        except Exception:
            self.chk_show_titlebar.set_active(True)
        general_box.append(self.chk_show_titlebar)

        self.chk_title_bottom = Gtk.CheckButton(label="Titlebar below terminal")
        try:
            self.chk_title_bottom.set_active(bool(self.config['title_at_bottom']))
        except Exception:
            self.chk_title_bottom.set_active(False)
        general_box.append(self.chk_title_bottom)

        # Selection & clipboard behavior
        row_clip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_clear_on_copy = Gtk.CheckButton(label="Clear selection after copy")
        try:
            self.chk_clear_on_copy.set_active(bool(self.config['clear_select_on_copy']))
        except Exception:
            self.chk_clear_on_copy.set_active(False)
        row_clip.append(self.chk_clear_on_copy)
        self.chk_disable_mouse_paste = Gtk.CheckButton(label="Disable mouse middle-click paste")
        try:
            self.chk_disable_mouse_paste.set_active(bool(self.config['disable_mouse_paste']))
        except Exception:
            self.chk_disable_mouse_paste.set_active(False)
        row_clip.append(self.chk_disable_mouse_paste)
        general_box.append(row_clip)

        # Window focus behavior
        row_focus = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_hide_on_lose = Gtk.CheckButton(label="Hide window when it loses focus")
        try:
            self.chk_hide_on_lose.set_active(bool(self.config['hide_on_lose_focus']))
        except Exception:
            self.chk_hide_on_lose.set_active(False)
        row_focus.append(self.chk_hide_on_lose)
        general_box.append(row_focus)

        # Link handling
        row_link = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_link_single = Gtk.CheckButton(label="Single-click opens links (with Ctrl)")
        try:
            self.chk_link_single.set_active(bool(self.config['link_single_click']))
        except Exception:
            self.chk_link_single.set_active(False)
        row_link.append(self.chk_link_single)
        general_box.append(row_link)

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
        self.chk_scroll_tabbar = Gtk.CheckButton(label="Scrollable tab bar")
        try:
            self.chk_scroll_tabbar.set_active(self.config['scroll_tabbar'])
        except Exception:
            self.chk_scroll_tabbar.set_active(False)
        row_tabbar1.append(self.chk_scroll_tabbar)
        self.chk_homog_tabbar = Gtk.CheckButton(label="Homogeneous tabs")
        try:
            self.chk_homog_tabbar.set_active(self.config['homogeneous_tabbar'])
        except Exception:
            self.chk_homog_tabbar.set_active(True)
        row_tabbar1.append(self.chk_homog_tabbar)
        general_box.append(row_tabbar1)

        # Tab behavior options
        row_tabbar2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_detachable_tabs = Gtk.CheckButton(label="Detachable tabs (drag to new window)")
        try:
            self.chk_detachable_tabs.set_active(self.config['detachable_tabs'])
        except Exception:
            self.chk_detachable_tabs.set_active(True)
        row_tabbar2.append(self.chk_detachable_tabs)
        self.chk_newtab_after_current = Gtk.CheckButton(label="Open new tab after current tab")
        try:
            self.chk_newtab_after_current.set_active(self.config['new_tab_after_current_tab'])
        except Exception:
            self.chk_newtab_after_current.set_active(False)
        row_tabbar2.append(self.chk_newtab_after_current)
        general_box.append(row_tabbar2)

        # Split behavior
        row_split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_split_with_profile = Gtk.CheckButton(label="Always split with current profile")
        try:
            self.chk_split_with_profile.set_active(self.config['always_split_with_profile'])
        except Exception:
            self.chk_split_with_profile.set_active(False)
        row_split.append(self.chk_split_with_profile)
        general_box.append(row_split)

        # Search options
        row_search = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_case_sensitive = Gtk.CheckButton(label="Case sensitive search")
        try:
            self.chk_case_sensitive.set_active(bool(self.config['case_sensitive']))
        except Exception:
            self.chk_case_sensitive.set_active(True)
        row_search.append(self.chk_case_sensitive)
        self.chk_invert_search = Gtk.CheckButton(label="Invert search direction")
        try:
            self.chk_invert_search.set_active(bool(self.config['invert_search']))
        except Exception:
            self.chk_invert_search.set_active(False)
        row_search.append(self.chk_invert_search)
        general_box.append(row_search)

        row_tabpos = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_tabpos.append(Gtk.Label(label="Tab position", xalign=0))
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
        row_close.append(Gtk.Label(label="Ask before closing", xalign=0))
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
        self.chk_close_btn = Gtk.CheckButton(label="Show close button on tab")
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
        notebook.append_page(scroller_general, Gtk.Label(label="General"))

        # Keybindings tab
        kb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
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
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            entry = Gtk.Entry()
            entry.set_hexpand(True)
            entry.set_placeholder_text("Press keys…")
            entry.set_text(self.config['keybindings'].get(key, '') or '')
            self._install_accel_capture(entry)
            row_box.append(entry)
            btn_clear = Gtk.Button(label="Clear")
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
        notebook.append_page(scroller_kb, Gtk.Label(label="Keybindings"))

        # Profiles tab (basic subset)
        prof_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        prof_box.set_margin_top(12)
        prof_box.set_margin_bottom(12)
        prof_box.set_margin_start(12)
        prof_box.set_margin_end(12)

        # Profile selector
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row1.append(Gtk.Label(label="Profile", xalign=0))
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
        self.chk_use_system_font = Gtk.CheckButton(label="Use system font")
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
        row_colors.append(Gtk.Label(label="Foreground", xalign=0))
        self.fg_btn = Gtk.ColorDialogButton()
        try:
            fg = Gdk.RGBA()
            fg.parse(self.config['foreground_color'])
            self.fg_btn.set_rgba(fg)
        except Exception:
            pass
        row_colors.append(self.fg_btn)
        row_colors.append(Gtk.Label(label="Background", xalign=0))
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
        self.chk_cursor_blink = Gtk.CheckButton(label="Cursor blink")
        try:
            self.chk_cursor_blink.set_active(self.config['cursor_blink'])
        except Exception:
            self.chk_cursor_blink.set_active(True)
        row_cursor.append(self.chk_cursor_blink)
        row_cursor.append(Gtk.Label(label="Cursor shape"))
        self.cursor_combo = Gtk.ComboBoxText()
        for key in ("block", "ibeam", "underline"):
            self.cursor_combo.append_text(key)
        try:
            curshape = self.config['cursor_shape']
            self.cursor_combo.set_active(["block","ibeam","underline"].index(curshape))
        except Exception:
            self.cursor_combo.set_active(0)
        row_cursor.append(self.cursor_combo)
        self.chk_bold_bright = Gtk.CheckButton(label="Bold is bright")
        try:
            self.chk_bold_bright.set_active(self.config['bold_is_bright'])
        except Exception:
            self.chk_bold_bright.set_active(False)
        row_cursor.append(self.chk_bold_bright)
        prof_box.append(row_cursor)

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
        self.chk_copy_on_select = Gtk.CheckButton(label="Copy on selection (profile)")
        try:
            self.chk_copy_on_select.set_active(bool(self.config['copy_on_selection']))
        except Exception:
            self.chk_copy_on_select.set_active(False)
        row_sel.append(self.chk_copy_on_select)
        prof_box.append(row_sel)

        # Scrollback
        row_scroll = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_scrollback_inf = Gtk.CheckButton(label="Infinite scrollback")
        try:
            self.chk_scrollback_inf.set_active(self.config['scrollback_infinite'])
        except Exception:
            self.chk_scrollback_inf.set_active(False)
        row_scroll.append(self.chk_scrollback_inf)
        row_scroll.append(Gtk.Label(label="Lines"))
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
        notebook.append_page(scroller_prof, Gtk.Label(label="Profiles"))
        
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

        # Plugins tab (enable/disable)
        plugins_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        plugins_box.set_margin_top(12)
        plugins_box.set_margin_bottom(12)
        plugins_box.set_margin_start(12)
        plugins_box.set_margin_end(12)

        self.plugin_checks = {}
        try:
            registry = PluginRegistry()
            registry.load_plugins(force=True)
            available = sorted(registry.get_available_plugins())
        except Exception:
            available = []
        enabled = set(self.config['enabled_plugins'] or [])
        for name in available:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            chk = Gtk.CheckButton(label=name)
            chk.set_active(name in enabled)
            row.append(chk)
            plugins_box.append(row)
            self.plugin_checks[name] = chk

        scroller_plugins = Gtk.ScrolledWindow()
        scroller_plugins.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller_plugins.set_child(plugins_box)
        scroller_plugins.set_hexpand(True)
        scroller_plugins.set_vexpand(True)
        notebook.append_page(scroller_plugins, Gtk.Label(label="Plugins"))

        # Buttons
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Save", Gtk.ResponseType.OK)
        self.connect("response", self.on_response)

        # Profile management actions (buttons under profile selector)
        try:
            pm_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            btn_add = Gtk.Button(label="Add…")
            btn_ren = Gtk.Button(label="Rename…")
            btn_del = Gtk.Button(label="Delete")
            pm_row.append(btn_add)
            pm_row.append(btn_ren)
            pm_row.append(btn_del)
            prof_box.append(pm_row)
            btn_add.connect('clicked', lambda b: self._on_profile_add())
            btn_ren.connect('clicked', lambda b: self._on_profile_rename())
            btn_del.connect('clicked', lambda b: self._on_profile_delete())
        except Exception:
            pass

    def _install_accel_capture(self, entry: Gtk.Entry):
        ctrl = Gtk.EventControllerKey()

        def on_key(controller, keyval, keycode, state):
            # Filter modifier-only presses
            mods = state & (
                Gdk.ModifierType.SHIFT_MASK |
                Gdk.ModifierType.CONTROL_MASK |
                Gdk.ModifierType.MOD1_MASK |
                Gdk.ModifierType.SUPER_MASK |
                Gdk.ModifierType.HYPER_MASK |
                Gdk.ModifierType.MOD2_MASK
            )
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
        dlg = Gtk.Dialog(title="Add Profile", transient_for=self, modal=True)
        box = dlg.get_content_area()
        entry = Gtk.Entry()
        entry.set_placeholder_text("Profile name")
        box.append(entry)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("Add", Gtk.ResponseType.OK)
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
        dlg = Gtk.Dialog(title="Rename Profile", transient_for=self, modal=True)
        box = dlg.get_content_area()
        entry = Gtk.Entry()
        entry.set_text(current)
        box.append(entry)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("Rename", Gtk.ResponseType.OK)
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
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("Delete", Gtk.ResponseType.OK)
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
