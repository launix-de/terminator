import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from .translation import _
from .config import Config


def show_custom_commands_dialog(plugin, parent_widget=None):
    """GTK4 dialog for Custom Commands plugin.

    Allows adding, editing, deleting and reordering commands. On Save,
    updates plugin.cmd_list and writes config via plugin._save_config().
    """

    # Build in-memory list from plugin.cmd_list preserving order
    items = [plugin.cmd_list[k] for k in sorted(plugin.cmd_list.keys())]

    dialog = Gtk.Dialog(title=_('Custom Commands Configuration'), modal=True,
                        transient_for=(parent_widget.get_root() if parent_widget else None))
    dialog.set_default_size(720, 420)
    box = dialog.get_content_area()
    box.set_spacing(8)

    # List of commands
    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

    def row_for_item(item):
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chk = Gtk.CheckButton()
        chk.set_active(bool(item.get('enabled', False)))
        hb.append(chk)
        name = Gtk.Label(label=item.get('name', ''), xalign=0)
        name.set_hexpand(True)
        hb.append(name)
        cmd = Gtk.Label(label=item.get('command', ''), xalign=0)
        cmd.add_css_class('dim-label')
        hb.append(cmd)
        row = Gtk.ListBoxRow()
        row.set_child(hb)
        # Store references
        row._item = item
        row._chk = chk
        row._name = name
        row._cmd = cmd
        return row

    def refresh_list():
        # Rebuild listbox children from items
        child = listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt
        for it in items:
            listbox.append(row_for_item(it))

    refresh_list()

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(listbox)
    scroller.set_vexpand(True)

    # Buttons panel
    btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    def get_selected_index():
        row = listbox.get_selected_row()
        if row is None:
            return -1
        # Find row index
        idx = 0
        r = listbox.get_first_child()
        while r is not None:
            if r is row:
                return idx
            idx += 1
            r = r.get_next_sibling()
        return -1

    def on_new(_b):
        it = edit_command_dialog(dialog)
        if it is not None:
            items.append(it)
            refresh_list()

    def on_edit(_b):
        idx = get_selected_index()
        if idx < 0:
            return
        cur = items[idx]
        it = edit_command_dialog(dialog, cur)
        if it is not None:
            items[idx] = it
            refresh_list()

    def on_delete(_b):
        idx = get_selected_index()
        if idx < 0:
            return
        items.pop(idx)
        refresh_list()

    def on_up(_b):
        idx = get_selected_index()
        if idx <= 0:
            return
        items[idx-1], items[idx] = items[idx], items[idx-1]
        refresh_list()
        listbox.select_row(listbox.get_row_at_index(idx-1))

    def on_down(_b):
        idx = get_selected_index()
        if idx < 0 or idx >= len(items)-1:
            return
        items[idx+1], items[idx] = items[idx], items[idx+1]
        refresh_list()
        listbox.select_row(listbox.get_row_at_index(idx+1))

    for label, cb in [(_('New'), on_new), (_('Edit'), on_edit), (_('Delete'), on_delete), (_('Up'), on_up), (_('Down'), on_down)]:
        b = Gtk.Button(label=label)
        b.connect('clicked', cb)
        btns.append(b)

    # Layout
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    hbox.append(scroller)
    hbox.append(btns)
    box.append(hbox)

    # Action buttons
    dialog.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)
    dialog.add_button(_('Save'), Gtk.ResponseType.OK)

    def write_back_and_save():
        # Update enabled flags from UI rows
        idx = 0
        r = listbox.get_first_child()
        while r is not None and idx < len(items):
            it = items[idx]
            try:
                it['enabled'] = bool(getattr(r, '_chk').get_active())
                # Keep name/command in sync with labels if edited via row
                it['name'] = getattr(r, '_name').get_text()
                it['command'] = getattr(r, '_cmd').get_text()
            except Exception:
                pass
            r = r.get_next_sibling()
            idx += 1
        # Rebuild plugin.cmd_list preserving new order
        plugin.cmd_list = {i: items[i] for i in range(len(items))}
        try:
            plugin._save_config()
        except Exception:
            pass

    def on_response(_dlg, resp):
        if resp == Gtk.ResponseType.OK:
            write_back_and_save()
        dialog.destroy()

    dialog.connect('response', on_response)
    dialog.present()


def edit_command_dialog(parent_dialog, item=None):
    """Return updated item dict or None if cancelled.
    item fields: enabled(bool), name(str), name_parse(bool), command(str)
    """
    it = item.copy() if isinstance(item, dict) else {'enabled': False, 'name': '', 'name_parse': False, 'command': ''}

    dlg = Gtk.Dialog(title=_('New Command') if item is None else _('Edit Command'), transient_for=parent_dialog, modal=True)
    box = dlg.get_content_area()
    box.set_spacing(8)
    grid = Gtk.Grid(column_spacing=8, row_spacing=8)

    row = 0
    chk_enabled = Gtk.CheckButton(label=_('Enabled'))
    chk_enabled.set_active(bool(it.get('enabled', False)))
    grid.attach(chk_enabled, 0, row, 2, 1)
    row += 1

    chk_parse = Gtk.CheckButton(label=_("Parse Name into SubMenu's"))
    chk_parse.set_active(bool(it.get('name_parse', False)))
    grid.attach(chk_parse, 0, row, 2, 1)
    row += 1

    grid.attach(Gtk.Label(label=_('Name'), xalign=0), 0, row, 1, 1)
    ent_name = Gtk.Entry()
    ent_name.set_hexpand(True)
    ent_name.set_text(it.get('name', ''))
    grid.attach(ent_name, 1, row, 1, 1)
    row += 1

    grid.attach(Gtk.Label(label=_('Command'), xalign=0), 0, row, 1, 1)
    tv = Gtk.TextView()
    buf = tv.get_buffer()
    buf.set_text(it.get('command', ''))
    tv.set_vexpand(True)
    sc = Gtk.ScrolledWindow()
    sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sc.set_child(tv)
    grid.attach(sc, 1, row, 1, 1)
    row += 1

    box.append(grid)
    dlg.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)
    dlg.add_button(_('OK'), Gtk.ResponseType.OK)

    def on_resp(d, resp):
        if resp == Gtk.ResponseType.OK:
            it['enabled'] = bool(chk_enabled.get_active())
            it['name'] = ent_name.get_text()
            it['name_parse'] = bool(chk_parse.get_active())
            start = buf.get_start_iter(); end = buf.get_end_iter()
            it['command'] = buf.get_text(start, end, True)
            d.destroy()
            return it
        d.destroy()
        return None

    result = {'value': None}
    def _on_resp(d, resp):
        result['value'] = on_resp(d, resp)
    dlg.connect('response', _on_resp)
    dlg.present()
    # Block until response to keep logic simple in this porting helper
    # In real GTK4, you’d prefer async; here we spin GTK loop
    while result['value'] is None and dlg.get_visible():
        while Gtk.events_pending():
            Gtk.main_iteration()
    return result['value']


def show_run_cmd_on_match_dialog(plugin, parent_widget=None):
    """GTK4 dialog for Run Command on Match plugin.

    Edits list of handlers: enabled, regexp, command. On save writes back
    to plugin.cmd_list and persists via plugin._save_config().
    """
    items = [plugin.cmd_list[k] for k in sorted(plugin.cmd_list.keys())]

    dialog = Gtk.Dialog(title=_('Run command on match Configuration'), modal=True,
                        transient_for=(parent_widget.get_root() if parent_widget else None))
    dialog.set_default_size(720, 420)
    box = dialog.get_content_area()
    box.set_spacing(8)

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

    def row_for_item(item):
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chk = Gtk.CheckButton()
        chk.set_active(bool(item.get('enabled', False)))
        hb.append(chk)
        rx = Gtk.Label(label=item.get('regexp', ''), xalign=0)
        rx.set_hexpand(True)
        hb.append(rx)
        cmd = Gtk.Label(label=item.get('command', ''), xalign=0)
        cmd.add_css_class('dim-label')
        hb.append(cmd)
        row = Gtk.ListBoxRow()
        row.set_child(hb)
        row._item = item
        row._chk = chk
        row._rx = rx
        row._cmd = cmd
        return row

    def refresh_list():
        child = listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt
        for it in items:
            listbox.append(row_for_item(it))

    refresh_list()

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(listbox)
    scroller.set_vexpand(True)

    btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

    def get_selected_index():
        row = listbox.get_selected_row()
        if row is None:
            return -1
        idx = 0
        r = listbox.get_first_child()
        while r is not None:
            if r is row:
                return idx
            idx += 1
            r = r.get_next_sibling()
        return -1

    def on_new(_b):
        it = edit_rcom_dialog(dialog)
        if it is not None:
            items.append(it)
            refresh_list()

    def on_edit(_b):
        idx = get_selected_index()
        if idx < 0:
            return
        cur = items[idx]
        it = edit_rcom_dialog(dialog, cur)
        if it is not None:
            items[idx] = it
            refresh_list()

    def on_delete(_b):
        idx = get_selected_index()
        if idx < 0:
            return
        items.pop(idx)
        refresh_list()

    def on_up(_b):
        idx = get_selected_index()
        if idx <= 0:
            return
        items[idx-1], items[idx] = items[idx], items[idx-1]
        refresh_list()
        listbox.select_row(listbox.get_row_at_index(idx-1))

    def on_down(_b):
        idx = get_selected_index()
        if idx < 0 or idx >= len(items)-1:
            return
        items[idx+1], items[idx] = items[idx], items[idx+1]
        refresh_list()
        listbox.select_row(listbox.get_row_at_index(idx+1))

    for label, cb in [(_('New'), on_new), (_('Edit'), on_edit), (_('Delete'), on_delete), (_('Up'), on_up), (_('Down'), on_down)]:
        b = Gtk.Button(label=label)
        b.connect('clicked', cb)
        btns.append(b)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    hbox.append(scroller)
    hbox.append(btns)
    box.append(hbox)

    dialog.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)
    dialog.add_button(_('Save'), Gtk.ResponseType.OK)

    def write_back_and_save():
        idx = 0
        r = listbox.get_first_child()
        while r is not None and idx < len(items):
            it = items[idx]
            try:
                it['enabled'] = bool(getattr(r, '_chk').get_active())
                it['regexp'] = getattr(r, '_rx').get_text()
                it['command'] = getattr(r, '_cmd').get_text()
            except Exception:
                pass
            r = r.get_next_sibling(); idx += 1
        plugin.cmd_list = {i: items[i] for i in range(len(items))}
        try:
            plugin._save_config()
        except Exception:
            pass

    def on_response(_dlg, resp):
        if resp == Gtk.ResponseType.OK:
            write_back_and_save()
        dialog.destroy()

    dialog.connect('response', on_response)
    dialog.present()


def edit_rcom_dialog(parent_dialog, item=None):
    it = item.copy() if isinstance(item, dict) else {'enabled': False, 'regexp': '', 'command': ''}
    dlg = Gtk.Dialog(title=_('New Command') if item is None else _('Edit Command'), transient_for=parent_dialog, modal=True)
    box = dlg.get_content_area()
    box.set_spacing(8)
    grid = Gtk.Grid(column_spacing=8, row_spacing=8)
    row = 0
    chk_enabled = Gtk.CheckButton(label=_('Enabled'))
    chk_enabled.set_active(bool(it.get('enabled', False)))
    grid.attach(chk_enabled, 0, row, 2, 1)
    row += 1
    grid.attach(Gtk.Label(label=_('regexp'), xalign=0), 0, row, 1, 1)
    ent_rx = Gtk.Entry(); ent_rx.set_hexpand(True); ent_rx.set_text(it.get('regexp', ''))
    grid.attach(ent_rx, 1, row, 1, 1)
    row += 1
    grid.attach(Gtk.Label(label=_('Command'), xalign=0), 0, row, 1, 1)
    ent_cmd = Gtk.Entry(); ent_cmd.set_hexpand(True); ent_cmd.set_text(it.get('command', ''))
    grid.attach(ent_cmd, 1, row, 1, 1)
    row += 1
    box.append(grid)
    dlg.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)
    dlg.add_button(_('OK'), Gtk.ResponseType.OK)
    result = {'value': None}
    def on_resp(d, resp):
        if resp == Gtk.ResponseType.OK:
            it['enabled'] = bool(chk_enabled.get_active())
            it['regexp'] = ent_rx.get_text()
            it['command'] = ent_cmd.get_text()
            d.destroy(); result['value'] = it; return
        d.destroy(); result['value'] = None
    dlg.connect('response', on_resp)
    dlg.present()
    while result['value'] is None and dlg.get_visible():
        while Gtk.events_pending():
            Gtk.main_iteration()
    return result['value']


def show_remote_prefs_dialog(plugin, parent_widget=None):
    """GTK4 Preferences for Remote plugin (auto_clone, infer_cwd, default profiles)."""
    from .config import Config as _Cfg
    cfg = _Cfg()
    profiles = []
    try:
        profiles = sorted(cfg.list_profiles(), key=str.lower)
    except Exception:
        profiles = ['default']
    cur = plugin.get_config()

    dlg = Gtk.Dialog(title=_('Remote Preferences'), modal=True,
                     transient_for=(parent_widget.get_root() if parent_widget else None))
    box = dlg.get_content_area(); box.set_spacing(8)
    grid = Gtk.Grid(column_spacing=8, row_spacing=8)
    row = 0
    chk_auto = Gtk.CheckButton(label=_('Clone On Split'))
    chk_auto.set_active(bool(cur.get('auto_clone', False)))
    grid.attach(chk_auto, 0, row, 2, 1); row += 1
    chk_infer = Gtk.CheckButton(label=_('Infer working directory on clone'))
    chk_infer.set_active(bool(cur.get('infer_cwd', True)))
    grid.attach(chk_infer, 0, row, 2, 1); row += 1

    grid.attach(Gtk.Label(label=_('Default SSH profile'), xalign=0), 0, row, 1, 1)
    combo_ssh = Gtk.ComboBoxText(); [combo_ssh.append_text(p) for p in profiles]
    try:
        combo_ssh.set_active(profiles.index(cur.get('ssh_default_profile') or 'default'))
    except Exception:
        combo_ssh.set_active(0)
    grid.attach(combo_ssh, 1, row, 1, 1); row += 1

    grid.attach(Gtk.Label(label=_('Default Container profile'), xalign=0), 0, row, 1, 1)
    combo_ctr = Gtk.ComboBoxText(); [combo_ctr.append_text(p) for p in profiles]
    try:
        combo_ctr.set_active(profiles.index(cur.get('container_default_profile') or 'default'))
    except Exception:
        combo_ctr.set_active(0)
    grid.attach(combo_ctr, 1, row, 1, 1); row += 1

    box.append(grid)
    dlg.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)
    dlg.add_button(_('Save'), Gtk.ResponseType.OK)

    def on_resp(d, resp):
        if resp == Gtk.ResponseType.OK:
            try:
                user = {
                    'auto_clone': str(bool(chk_auto.get_active())),
                    'infer_cwd': str(bool(chk_infer.get_active())),
                    'ssh_default_profile': combo_ssh.get_active_text() or '',
                    'container_default_profile': combo_ctr.get_active_text() or '',
                }
                cfg.plugin_set_config(plugin.__class__.__name__, user)
                cfg.save()
                plugin.config = plugin.get_config()
            except Exception:
                pass
        d.destroy()
    dlg.connect('response', on_resp)
    dlg.present()
