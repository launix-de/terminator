"""GTK 4 terminal context menu, ported structure from the original menu.

Builds a Gio.MenuModel/Gtk.PopoverMenu and uses the terminal's action group
(`term.*` actions) to execute behaviors, matching the original layout.
Plugin menus are integrated via `plugin_gtk4_adapter.build_plugin_menu_for_terminal`.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Vte', '3.91')
from gi.repository import Gtk, Gio, GLib

from .translation import _
from .config import Config
from .plugin_gtk4_adapter import build_plugin_menu_for_terminal


def build_menu_model(terminal) -> Gio.MenuModel:
    cfg = Config()
    menu = Gio.Menu()

    # Clipboard
    sec1 = Gio.Menu()
    sec1.append(_('_Copy'), 'term.copy')
    sec1.append(_('_Copy as HTML'), 'term.copy_html')
    sec1.append(_('_Paste'), 'term.paste')
    sec1.append(_('Paste Se_lection'), 'term.paste_selection')
    menu.append_section(None, sec1)

    # Actions
    sec2 = Gio.Menu()
    sec2.append(_('Set _Window Title'), 'term.edit_window_title')
    sec2.append(_('Set _Tab Title'), 'term.edit_tab_title')
    sec2.append(_('_Find…'), 'term.search')
    sec2.append(_('Find _Next'), 'term.find_next')
    sec2.append(_('Find _Previous'), 'term.find_previous')
    sec2.append(_('Find _Next'), 'term.find_next')
    sec2.append(_('Find _Previous'), 'term.find_previous')
    sec2.append(_('Split _Auto'), 'term.split_auto')
    sec2.append(_('Split H_orizontally'), 'term.split_horiz')
    sec2.append(_('Split V_ertically'), 'term.split_vert')
    sec2.append(_('Open _Tab'), 'term.new_tab')
    sec2.append(_('_Reset'), 'term.reset')
    sec2.append(_('Reset and _Clear'), 'term.reset_clear')
    sec2.append(_('_Close'), 'term.close')
    menu.append_section(None, sec2)

    # View
    sec3 = Gio.Menu()
    sec3.append(_('_Zoom terminal'), 'term.zoom')
    sec3.append(_('Ma_ximize terminal'), 'term.maximize')
    sec3.append(_('_Full Screen'), 'term.full_screen')
    menu.append_section(None, sec3)

    # Toggles / Preferences
    sec4 = Gio.Menu()
    sec4.append(_('_Read only'), 'term.toggle_readonly')
    sec4.append(_('Show _scrollbar'), 'term.toggle_scrollbar')
    sec4.append(_('_Preferences'), 'term.preferences')
    sec4.append(_('New _Window'), 'term.new_window')
    sec4.append(_('_Hide Window'), 'term.hide_window')

    # Profiles submenu
    profiles = sorted(cfg.list_profiles(), key=str.lower)
    if len(profiles) > 1:
        prof = Gio.Menu()
        for p in profiles:
            it = Gio.MenuItem.new(p, None)
            it.set_attribute_value('action', GLib.Variant('s', 'term.profile'))
            it.set_attribute_value('target', GLib.Variant('s', p))
            prof.append_item(it)
        sec4.append_submenu(_('Profiles'), prof)

    # Layouts submenu
    try:
        layouts = cfg.list_layouts()
        if layouts:
            lay = Gio.Menu()
            for l in layouts:
                it = Gio.MenuItem.new(l, None)
                it.set_attribute_value('action', GLib.Variant('s', 'term.layout'))
                it.set_attribute_value('target', GLib.Variant('s', l))
                lay.append_item(it)
            sec4.append_submenu(_('Layouts...'), lay)
    except Exception:
        pass

    menu.append_section(None, sec4)

    # Grouping
    sec5 = Gio.Menu()
    sec5.append(_('Create _Group…'), 'term.create_group')
    sec5.append(_('Group all in _window'), 'term.group_all_window')
    sec5.append(_('Ungroup all in w_indow'), 'term.ungroup_all_window')
    sec5.append(_('Group all in _tab'), 'term.group_all_tab')
    sec5.append(_('Ungroup all in t_ab'), 'term.ungroup_all_tab')

    # Broadcast submenu
    bmenu = Gio.Menu()
    bmenu.append(_('Broadcast _off'), 'term.groupsend_off')
    bmenu.append(_('Broadcast to _group'), 'term.groupsend_group')
    bmenu.append(_('Broadcast to _all'), 'term.groupsend_all')
    sec5.append_submenu(_('Broadcast'), bmenu)

    menu.append_section(_('Grouping'), sec5)

    # Plugins (if any)
    try:
        plugin_menu, actions = build_plugin_menu_for_terminal(terminal)
    except Exception:
        plugin_menu, actions = None, []
    if plugin_menu is not None:
        menu.append_section(_('Plugins'), plugin_menu)
        # Install actions on terminal's action group (simple and toggle)
        ag = getattr(terminal, '_action_group', None)
        if ag is not None:
            for entry in actions:
                try:
                    # Backward compatibility with (name, cb)
                    if isinstance(entry, tuple) and len(entry) == 2 and callable(entry[1]):
                        name, cb = entry
                        if ag.lookup_action(name) is None:
                            act = Gio.SimpleAction.new(name, None)
                            act.connect('activate', cb)
                            ag.add_action(act)
                        continue
                    # New structured definitions
                    kind = entry[1]
                    if kind == 'simple':
                        name, _k, cb = entry
                        if ag.lookup_action(name) is None:
                            act = Gio.SimpleAction.new(name, None)
                            act.connect('activate', cb)
                            ag.add_action(act)
                    elif kind == 'toggle':
                        name, _k, initial, change_cb = entry
                        if ag.lookup_action(name) is None:
                            act = Gio.SimpleAction.new_stateful(name, None, GLib.Variant('b', bool(initial)))
                            act.connect('change-state', change_cb)
                            ag.add_action(act)
                    elif kind == 'radio':
                        name, _k, initial, change_cb = entry
                        if ag.lookup_action(name) is None:
                            act = Gio.SimpleAction.new_stateful(name, GLib.VariantType.new('s'), GLib.Variant('s', str(initial)))
                            act.connect('change-state', change_cb)
                            ag.add_action(act)
                except Exception:
                    continue
    # Help
    secH = Gio.Menu()
    secH.append(_('_Help'), 'term.help')
    menu.append_section(None, secH)

    return menu


def popup_for_terminal(terminal, x=0, y=0):
    pop = Gtk.PopoverMenu.new_from_model(build_menu_model(terminal))
    pop.set_parent(terminal)
    rect = Gtk.Rectangle()
    rect.x = int(x)
    rect.y = int(y)
    rect.width = rect.height = 1
    pop.set_pointing_to(rect)
    pop.popup()
    return pop
