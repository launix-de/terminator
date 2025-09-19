"""Minimal GTK4 Window hosting a single VTE terminal.

This is a stepping stone toward a full GTK4 port. It purposefully
implements only a small subset of behaviors so we can iterate.
"""

from gi.repository import Gtk

from .gtk4terminal import Gtk4Terminal


class TerminatorGtk4Window(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("Terminator")
        self.set_default_size(1000, 700)
        self.root = None
        self._install_shortcuts()

        # Layout: simple box with one terminal for now
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_hexpand(True)
        root.set_vexpand(True)
        self.set_child(root)
        self.root = root

        term = Gtk4Terminal()
        self.term = term
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_child(term)
        term.set_hexpand(True)
        term.set_vexpand(True)
        term.set_scroller(scroller)

        # In Gtk4, append replaces pack_* and add
        root.append(scroller)

        # Close window when the child exits
        term.connect("child-exited", self.on_child_exited)

        # Spawn user's shell
        term.spawn_login_shell()

    def on_child_exited(self, term, status):
        # If there are multiple terminals, remove just this one; else close
        scroller = term.get_parent()
        container = scroller.get_parent()
        if isinstance(container, Gtk.Paned):
            other = container.get_start_child() if container.get_end_child() is scroller else container.get_end_child()
            parent = container.get_parent()
            if isinstance(parent, Gtk.Paned):
                if parent.get_start_child() is container:
                    parent.set_start_child(other)
                else:
                    parent.set_end_child(other)
            elif isinstance(parent, Gtk.Box):
                parent.remove(container)
                parent.append(other)
            container.set_start_child(None)
            container.set_end_child(None)
        else:
            try:
                self.close()
            except Exception:
                pass

    def _new_terminal_scroller(self):
        term = Gtk4Terminal()
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_child(term)
        term.set_hexpand(True)
        term.set_vexpand(True)
        term.set_scroller(scroller)
        term.connect("child-exited", self.on_child_exited)
        term.spawn_login_shell()
        return term, scroller

    def _install_shortcuts(self):
        # Install configurable shortcuts mapped from Config keybindings
        from .config import Config
        cfg = Config()

        def add_shortcut(trigger_str, callback):
            if not trigger_str:
                return
            # Normalize some modifier names
            trig = Gtk.ShortcutTrigger.parse_string(trigger_str.replace('Primary', 'Control'))
            if not trig:
                return
            ctrl = Gtk.ShortcutController()
            ctrl.add_shortcut(Gtk.Shortcut.new(trig, Gtk.CallbackAction.new(callback)))
            self.add_controller(ctrl)

        # Tabs next/prev
        add_shortcut(cfg['keybindings'].get('next_tab'), self._on_tab_next)
        add_shortcut(cfg['keybindings'].get('prev_tab'), self._on_tab_prev)

        # New tab
        add_shortcut(cfg['keybindings'].get('new_tab'), self._on_new_tab)

        # Splits
        add_shortcut(cfg['keybindings'].get('split_horiz'), lambda *a: self._on_split(Gtk.Orientation.HORIZONTAL))
        add_shortcut(cfg['keybindings'].get('split_vert'), lambda *a: self._on_split(Gtk.Orientation.VERTICAL))

        # Close window and terminal
        add_shortcut(cfg['keybindings'].get('close_window'), self._on_close_window)
        add_shortcut(cfg['keybindings'].get('close_term'), self._on_close_term)

        # Copy / Paste
        add_shortcut(cfg['keybindings'].get('copy'), self._on_copy)
        add_shortcut(cfg['keybindings'].get('paste'), self._on_paste)

        # Toggle scrollbar
        add_shortcut(cfg['keybindings'].get('toggle_scrollbar'), self._on_toggle_scrollbar)

        # Full screen
        add_shortcut(cfg['keybindings'].get('full_screen'), self._on_full_screen)

        # Preferences / Edit window title
        add_shortcut(cfg['keybindings'].get('preferences_keybindings'), self._on_preferences)
        add_shortcut(cfg['keybindings'].get('edit_window_title'), self._on_edit_window_title)

    def refresh_shortcuts(self):
        # Remove all existing ShortcutControllers and reinstall from Config
        controllers = [c for c in self.observe_controllers()]
        for c in controllers:
            if isinstance(c, Gtk.ShortcutController):
                self.remove_controller(c)
        self._install_shortcuts()

    def _on_tab_next(self, *args):
        child = self.get_child()
        if isinstance(child, Gtk.Notebook) and child.get_n_pages() > 0:
            i = child.get_current_page()
            child.set_current_page((i + 1) % child.get_n_pages())
        return True

    def _on_tab_prev(self, *args):
        child = self.get_child()
        if isinstance(child, Gtk.Notebook) and child.get_n_pages() > 0:
            i = child.get_current_page()
            child.set_current_page((i - 1) % child.get_n_pages())
        return True

    def _on_new_tab(self, *args):
        self.open_new_tab()
        return True

    def _get_focused_terminal(self):
        # Walk up from focus widget to find a Gtk4Terminal
        focus = self.get_focus()
        from .gtk4terminal import Gtk4Terminal
        w = focus
        while w is not None and not isinstance(w, Gtk4Terminal):
            w = w.get_parent()
        return w

    def _on_split(self, orientation):
        term = self._get_focused_terminal()
        if term is not None:
            self.split_terminal(term, orientation)
        return True

    def _on_close_window(self, *args):
        self.close()
        return True

    def _on_close_term(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            # Attempt to terminate the shell in this terminal
            try:
                term.feed_child("exit\n")
            except Exception:
                # Fallback: collapse pane or close window
                self.on_child_exited(term, 0)
        return True

    def _on_copy(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            try:
                term.copy_clipboard()
            except Exception:
                pass
        return True

    def _on_paste(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            try:
                term.paste_clipboard()
            except Exception:
                pass
        return True

    def _on_toggle_scrollbar(self, *args):
        term = self._get_focused_terminal()
        if term is not None:
            scroller = term.get_parent()
            if isinstance(scroller, Gtk.ScrolledWindow):
                # Toggle between automatic and never
                hp, vp = scroller.get_policy()
                new_policy = Gtk.PolicyType.NEVER if hp != Gtk.PolicyType.NEVER else Gtk.PolicyType.AUTOMATIC
                scroller.set_policy(new_policy, Gtk.PolicyType.AUTOMATIC)
        return True

    def _on_full_screen(self, *args):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()
        return True

    def _on_preferences(self, *args):
        from .preferences_gtk4 import PreferencesWindow
        dlg = PreferencesWindow(parent=self)
        dlg.present()
        return True

    def _on_edit_window_title(self, *args):
        # Reuse the terminal action by invoking its handler if possible
        term = self._get_focused_terminal()
        if term is not None:
            act = term._action_group.lookup_action("edit_window_title") if hasattr(term, "_action_group") else None
            if act:
                act.activate(None)
                return True
        # Fallback: simple dialog
        dialog = Gtk.Dialog(title="Set Window Title", transient_for=self, modal=True)
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
                    self.set_title(txt)
            dlg.destroy()
        dialog.connect("response", on_response)
        dialog.present()
        return True

    def split_terminal(self, term: Gtk4Terminal, orientation: Gtk.Orientation):
        scroller = term.get_parent()
        parent = scroller.get_parent()
        new_term, new_scroller = self._new_terminal_scroller()
        paned = Gtk.Paned(orientation=orientation)

        # For Gtk.Box, remember insertion position before removing
        insert_after = None
        if isinstance(parent, Gtk.Box):
            child = parent.get_first_child()
            prev = None
            while child is not None and child is not scroller:
                prev = child
                child = child.get_next_sibling()
            insert_after = prev

        # Detach scroller from its current parent before reparenting
        if isinstance(parent, Gtk.Paned):
            if parent.get_start_child() is scroller:
                parent.set_start_child(None)
            else:
                parent.set_end_child(None)
        elif isinstance(parent, Gtk.Box):
            parent.remove(scroller)
        elif isinstance(parent, Gtk.Notebook):
            # Replace in the current notebook page
            idx = -1
            for i in range(parent.get_n_pages()):
                if parent.get_nth_page(i) is scroller:
                    idx = i
                    break
            if idx >= 0:
                parent.remove_page(idx)

        paned.set_start_child(scroller)
        paned.set_end_child(new_scroller)
        paned.set_resize_start_child(True)
        paned.set_resize_end_child(True)

        if isinstance(parent, Gtk.Paned):
            # Replace in same slot
            # Note: at this point, parent's child slot is empty
            if parent.get_start_child() is None:
                parent.set_start_child(paned)
            elif parent.get_end_child() is None:
                parent.set_end_child(paned)
            else:
                # Fallback: set end child
                parent.set_end_child(paned)
        elif isinstance(parent, Gtk.Box):
            if insert_after is None:
                parent.prepend(paned)
            else:
                parent.insert_child_after(paned, insert_after)
        elif isinstance(parent, Gtk.Notebook):
            # Insert into the same page index (or at end if unknown)
            page_label = Gtk.Label(label=str((idx if idx >= 0 else parent.get_n_pages()) + 1))
            if idx >= 0:
                parent.insert_page(paned, page_label, idx)
                parent.set_current_page(idx)
            else:
                parent.append_page(paned, page_label)
        else:
            self.set_child(paned)

        new_term.grab_focus()

    def zoom_terminal(self, term: Gtk4Terminal):
        # TODO: implement zoom toggle using a revealer or overlay
        pass

    def open_new_tab(self):
        child = self.get_child()
        notebook = None
        if isinstance(child, Gtk.Notebook):
            notebook = child
        else:
            # Convert current content into a notebook
            notebook = Gtk.Notebook()
            notebook.set_hexpand(True)
            notebook.set_vexpand(True)
            # Move existing child into first tab
            if isinstance(child, Gtk.Box):
                # Assume first child is the scroller/paned
                existing = child.get_first_child()
                if existing is not None:
                    child.remove(existing)
                self.set_child(notebook)
                if existing is not None:
                    notebook.append_page(existing, Gtk.Label(label="1"))
            else:
                self.set_child(notebook)

        # Add new page
        term, scroller = self._new_terminal_scroller()
        page_num = notebook.append_page(scroller, Gtk.Label(label=str(notebook.get_n_pages()+1)))
        notebook.set_current_page(page_num)
