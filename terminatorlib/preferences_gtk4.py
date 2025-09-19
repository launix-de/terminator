"""GTK 4 Preferences window (initial subset).

This dialog provides a minimal set of preferences to unblock the port:
- General: a few global toggles
- Keybindings: edit a handful of common actions (new tab, split horiz/vert, close term)

It updates terminatorlib.config.Config and asks the window to refresh shortcuts.
"""

from gi.repository import Gtk, Gdk

from .config import Config, DEFAULTS


class PreferencesWindow(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window | None = None):
        super().__init__(title="Preferences", transient_for=parent, modal=True)
        self.set_default_size(700, 500)
        self.config = Config()

        area = self.get_content_area()
        area.set_spacing(12)
        notebook = Gtk.Notebook()
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

        notebook.append_page(general_box, Gtk.Label(label="General"))

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

        notebook.append_page(kb_box, Gtk.Label(label="Keybindings"))

        # Buttons
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Save", Gtk.ResponseType.OK)
        self.connect("response", self.on_response)

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
        if response_id == Gtk.ResponseType.OK:
            # Save general options
            self.config['always_on_top'] = self.chk_always_on_top.get_active()
            self.config['hide_from_taskbar'] = self.chk_hide_taskbar.get_active()
            # Save keybindings subset
            kb = self.config['keybindings']
            # Detect duplicates among non-empty values
            values = {}
            for key, entry in self.kb_entries.items():
                accel = entry.get_text().strip()
                # normalize accelerator for comparison
                if accel:
                    kv, mods = Gtk.accelerator_parse(accel)
                    accel = Gtk.accelerator_name(kv, mods) if kv != 0 else accel
                if accel:
                    if accel in values:
                        # Show message and abort save
                        self._show_duplicate_dialog(accel, values[accel], key)
                        return
                    values[accel] = key
                kb[key] = accel
            # Persist
            self.config.save()
            # Ask parent to refresh shortcuts, if it supports it
            parent = self.get_transient_for()
            if parent and hasattr(parent, 'refresh_shortcuts'):
                parent.refresh_shortcuts()
        self.destroy()

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
