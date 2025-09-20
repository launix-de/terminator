# Plugin by Sinan Nalkaya <sardok@gmail.com>
# See LICENSE of Terminator package.

""" logger.py - Terminator Plugin to log 'content' of individual
terminals """

import os
import sys
import gi
try:
    gi.require_version('Vte', '3.91')
except Exception:
    try:
        gi.require_version('Vte', '2.91')
    except Exception:
        pass
from gi.repository import Gtk, Vte
import terminatorlib.plugin as plugin
from terminatorlib.translation import _

AVAILABLE = ['Logger']

class Logger(plugin.MenuItem):
    """ Add custom command to the terminal menu"""
    capabilities = ['terminal_menu']
    loggers = None
    dialog_action = Gtk.FileChooserAction.SAVE
    dialog_buttons = (_("_Cancel"), Gtk.ResponseType.CANCEL,
                      _("_Save"), Gtk.ResponseType.OK)
    vte_version = Vte.get_minor_version()

    def __init__(self):
        plugin.MenuItem.__init__(self)
        if not self.loggers:
            self.loggers = {}

    def callback(self, menuitems, menu, terminal):
        """ Add save menu item to the menu"""
        vte_terminal = terminal.get_vte()
        if vte_terminal not in self.loggers:
            item = Gtk.MenuItem.new_with_mnemonic(_('Start _Logger'))
            item.connect("activate", self.start_logger, terminal)
        else:
            item = Gtk.MenuItem.new_with_mnemonic(_('Stop _Logger'))
            item.connect("activate", self.stop_logger, terminal)
            item.set_has_tooltip(True)
            item.set_tooltip_text("Saving at '" + self.loggers[vte_terminal]["filepath"] + "'")
        menuitems.append(item)
        
    def write_content(self, terminal, row_start, col_start, row_end, col_end):
        """ Final function to write a file """
        if self.vte_version < 72:
            content = terminal.get_text_range(row_start, col_start, row_end, col_end,
                                          lambda *a: True)
        else:
            content = terminal.get_text_range_format(Vte.Format.TEXT,row_start, col_start, row_end, col_end)
        content = content[0]
        fd = self.loggers[terminal]["fd"]
        # Don't write the last char which is always '\n'
        fd.write(content[:-1])
        self.loggers[terminal]["col"] = col_end
        self.loggers[terminal]["row"] = row_end

    def save(self, terminal):
        """ 'contents-changed' callback """
        last_saved_col = self.loggers[terminal]["col"]
        last_saved_row = self.loggers[terminal]["row"]
        (col, row) = terminal.get_cursor_position()
        # Save only when buffer is nearly full,
        # for the sake of efficiency
        if row - last_saved_row < terminal.get_row_count():
            return
        self.write_content(terminal, last_saved_row, last_saved_col, row, col)
        
    def start_logger(self, _widget, Terminal):
        """ Handle menu item callback by saving text to a file"""
        logfile = None
        # Prefer GTK4 FileDialog if available
        try:
            if hasattr(Gtk, 'FileDialog'):
                from gi.repository import GLib
                file_dialog = Gtk.FileDialog(title=_("Save Log File As"))
                result = {'path': None}
                def on_done(dlg, res):
                    try:
                        gfile = dlg.save_finish(res)
                        if gfile is not None:
                            result['path'] = gfile.get_path()
                    except Exception:
                        result['path'] = None
                loop = GLib.MainLoop()
                def _cb(dlg, res):
                    on_done(dlg, res)
                    try:
                        loop.quit()
                    except Exception:
                        pass
                file_dialog.save(_widget.get_toplevel(), None, _cb)
                loop.run()
                logfile = result['path']
            else:
                raise AttributeError
        except Exception:
            savedialog = Gtk.FileChooserDialog(title=_("Save Log File As"),
                                               action=self.dialog_action,
                                               buttons=self.dialog_buttons)
            savedialog.set_transient_for(_widget.get_toplevel())
            savedialog.set_do_overwrite_confirmation(True)
            savedialog.set_local_only(True)
            savedialog.show_all()
            response = savedialog.run()
            if response == Gtk.ResponseType.OK:
                logfile = os.path.join(savedialog.get_current_folder(),
                                       savedialog.get_filename())
            savedialog.destroy()

        if logfile:
            try:
                fd = open(logfile, 'w+')
                vte_terminal = Terminal.get_vte()
                (col, row) = vte_terminal.get_cursor_position()
                self.loggers[vte_terminal] = {"filepath":logfile,
                                              "handler_id":0, "fd":fd,
                                              "col":col, "row":row}
                self.loggers[vte_terminal]["handler_id"] = vte_terminal.connect('contents-changed', self.save)
            except Exception as e:
                error = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR,
                                          Gtk.ButtonsType.OK, str(e))
                error.set_transient_for(_widget.get_toplevel())
                error.run()
                error.destroy()

    def stop_logger(self, _widget, terminal):
        vte_terminal = terminal.get_vte()
        last_saved_col = self.loggers[vte_terminal]["col"]
        last_saved_row = self.loggers[vte_terminal]["row"]
        (col, row) = vte_terminal.get_cursor_position()
        if last_saved_col != col or last_saved_row != row:
            # Save unwritten buffer to the file
            self.write_content(vte_terminal, last_saved_row, last_saved_col, row, col)
        fd = self.loggers[vte_terminal]["fd"]
        fd.close()
        vte_terminal.disconnect(self.loggers[vte_terminal]["handler_id"])
        del(self.loggers[vte_terminal])
