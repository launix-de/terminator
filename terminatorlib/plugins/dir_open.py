from terminatorlib.translation import _
import terminatorlib.plugin as plugin

AVAILABLE = ['CurrDirOpen']


class CurrDirOpen(plugin.MenuItem):
    capabilities = ['terminal_menu']
    config = None

    def __init__(self):
        self.cwd = ""
        self.terminal = None

    def _on_menu_item_add_tag_activate(self, _menu_item_add_tag):
        if not self.cwd:
            return
        # Delegate to terminal helper which respects custom URL handlers
        try:
            self.terminal.open_url("file://" + self.cwd)
        except Exception:
            pass

    def callback(self, menuitems, menu, terminal):
        self.cwd = terminal.get_cwd()
        self.terminal = terminal

        try:
            # The GTK4 adapter shims Gtk.MenuItem.new_with_mnemonic
            from gi.repository import Gtk  # type: ignore
            item = Gtk.MenuItem.new_with_mnemonic(_('Open current _directory'))
        except Exception:
            # Fallback: simple object provided by adapter
            class _Stub:
                def __init__(self, label):
                    self._label = label
                def connect(self, *a, **kw):
                    return None
            item = _Stub(_('Open current directory'))
        try:
            item.connect("activate", self._on_menu_item_add_tag_activate)
        except Exception:
            pass
        menuitems.append(item)
