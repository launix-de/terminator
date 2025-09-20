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
        # Try GTK4 snapshot path first
        orig_pixbuf = None
        snapshot_texture = None
        try:
            # Render widget to a texture via GSK and save as PNG
            from gi.repository import Gsk, Graphene, Gdk
            # Ensure widget has a valid allocation
            w = getattr(terminal, 'get_allocated_width', lambda: 0)()
            h = getattr(terminal, 'get_allocated_height', lambda: 0)()
            if w <= 0 or h <= 0:
                terminal.queue_allocate()
                # Let GTK flush a frame
                while Gtk.events_pending():
                    Gtk.main_iteration_do(False)
                w = getattr(terminal, 'get_allocated_width', lambda: 0)()
                h = getattr(terminal, 'get_allocated_height', lambda: 0)()
            native = terminal.get_native() if hasattr(terminal, 'get_native') else None
            surface = native.get_surface() if native and hasattr(native, 'get_surface') else None
            if surface is None or w <= 0 or h <= 0:
                raise RuntimeError('No native surface or invalid size')
            snap = Gtk.Snapshot.new()
            # Snapshot the widget subtree
            terminal.snapshot(snap)
            node = snap.to_node()
            renderer = None
            try:
                renderer = Gsk.Renderer.for_surface(surface)
            except Exception:
                try:
                    renderer = Gsk.Renderer.new_for_surface(surface)
                except Exception:
                    pass
            if renderer is None:
                raise RuntimeError('No GSK renderer')
            # Viewport: full widget area
            rect = Graphene.Rect()
            rect.init(0.0, 0.0, float(w), float(h))
            texture = renderer.render_texture(node, rect)
            # Keep texture for saving
            snapshot_texture = texture
        except Exception:
            snapshot_texture = None

        if snapshot_tempfile is None:
            # Fallback: GTK3 utility path using cairo/Gdk (may fail on GTK4)
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
                if snapshot_texture is not None:
                    # Prefer direct texture save; fallback to download+pixbuf
                    try:
                        # GTK 4.10+: Gdk.Texture.save_to_png
                        snapshot_texture.save_to_png(path)
                        return
                    except Exception:
                        try:
                            # Fallback: download pixel data and encode as PNG via Pixbuf
                            from gi.repository import Gdk, GdkPixbuf, GLib
                            w = snapshot_texture.get_width(); h = snapshot_texture.get_height()
                            # Download returns bytes in RGBA
                            data = bytearray(w*h*4)
                            snapshot_texture.download(memoryview(data), w*4)
                            pb = GdkPixbuf.Pixbuf.new_from_bytes(
                                GLib.Bytes.new(bytes(data)),
                                GdkPixbuf.Colorspace.RGB,
                                True, 8, w, h, w*4
                            )
                            pb.savev(path, 'png', [], [])
                            return
                        except Exception:
                            pass
                # Fallback: save pixbuf
                if orig_pixbuf is not None:
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
