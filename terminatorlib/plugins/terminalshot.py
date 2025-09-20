# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminalshot.py - Terminator Plugin to take 'screenshots' of individual
terminals"""

import os
import gi
from gi.repository import Gtk
from gi.repository import GdkPixbuf, GLib
import terminatorlib.plugin as plugin
from terminatorlib.translation import _
from terminatorlib.util import widget_pixbuf

# Every plugin you want Terminator to load *must* be listed in 'AVAILABLE'
AVAILABLE = ['TerminalShot']

class TerminalShot(plugin.MenuItem):
    """Add custom commands to the terminal menu"""
    capabilities = ['terminal_menu']
    dialog_action = Gtk.FileChooserAction.SAVE
    dialog_buttons = (_("_Cancel"), Gtk.ResponseType.CANCEL,
                      _("_Save"), Gtk.ResponseType.OK)

    def __init__(self):
        plugin.MenuItem.__init__(self)

    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        item = Gtk.MenuItem.new_with_mnemonic(_('Terminal _screenshot'))
        item.connect("activate", self.terminalshot, terminal)
        menuitems.append(item)

    def terminalshot(self, _widget, terminal):
        """Handle the taking, prompting and saving of a terminalshot"""
        # Grab a pixbuf of the terminal (GTK3 util); GTK4 may not support this path
        try:
            orig_pixbuf = widget_pixbuf(terminal)
        except Exception as e:
            errdlg = Gtk.MessageDialog(transient_for=(terminal.get_root() if hasattr(terminal, 'get_root') else None),
                                       modal=True,
                                       message_type=Gtk.MessageType.ERROR,
                                       buttons=Gtk.ButtonsType.OK,
                                       text=_('Terminal screenshot is not available on this backend.'))
            errdlg.format_secondary_text(str(e))
            errdlg.connect('response', lambda d, r: d.destroy())
            errdlg.present()
            return

        path = None
        # Prefer GTK4 FileDialog if available
        try:
            if hasattr(Gtk, 'FileDialog'):
                file_dialog = Gtk.FileDialog(title=_("Save image"))
                result = {'path': None}
                loop = GLib.MainLoop()
                def on_done(dlg, res):
                    try:
                        gfile = dlg.save_finish(res)
                        if gfile is not None:
                            result['path'] = gfile.get_path()
                    except Exception:
                        result['path'] = None
                    try:
                        loop.quit()
                    except Exception:
                        pass
                parent = terminal.get_root() if hasattr(terminal, 'get_root') else None
                file_dialog.save(parent, None, on_done)
                loop.run()
                path = result['path']
            else:
                raise AttributeError
        except Exception:
            savedialog = Gtk.FileChooserDialog(title=_("Save image"),
                                               action=self.dialog_action,
                                               buttons=self.dialog_buttons)
            try:
                if _widget is not None:
                    savedialog.set_transient_for(_widget.get_toplevel())
            except Exception:
                pass
            savedialog.set_do_overwrite_confirmation(True)
            savedialog.set_local_only(True)
            try:
                # Show a small preview
                pixbuf = orig_pixbuf.scale_simple(max(1, orig_pixbuf.get_width() // 2),
                                                  max(1, orig_pixbuf.get_height() // 2),
                                                  GdkPixbuf.InterpType.BILINEAR)
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                savedialog.set_preview_widget(image)
            except Exception:
                pass
            savedialog.show_all()
            response = savedialog.run()
            if response == Gtk.ResponseType.OK:
                path = os.path.join(savedialog.get_current_folder(),
                                    savedialog.get_filename())
            savedialog.destroy()

        if path:
            try:
                # Ensure .png extension
                if not path.lower().endswith('.png'):
                    path += '.png'
                orig_pixbuf.savev(path, 'png', [], [])
            except Exception as e:
                errdlg = Gtk.MessageDialog(transient_for=(terminal.get_root() if hasattr(terminal, 'get_root') else None),
                                           modal=True,
                                           message_type=Gtk.MessageType.ERROR,
                                           buttons=Gtk.ButtonsType.OK,
                                           text=_('Failed to save image'))
                errdlg.format_secondary_text(str(e))
                errdlg.connect('response', lambda d, r: d.destroy())
                errdlg.present()
