mod model;
mod ui;

use crate::model::{ActionId, KeybindingMap, TabId, WindowId, WorkspaceModel};
use gtk4::{
    Application, ApplicationWindow, Box, Dialog, Entry, GestureClick, Label, ListBox, ListBoxRow,
    Orientation, PopoverMenu, ResponseType, gdk, gio, glib, prelude::*,
};
use std::{cell::RefCell, rc::Rc};
use ui::EditableTitleBar;
use vte4::{Format, PtyFlags, Terminal, prelude::*};

const ACTION_DEFS: &[(ActionId, &str)] = &[
    (ActionId::Copy, "Copy"),
    (ActionId::Paste, "Paste"),
    (ActionId::NewWindow, "New Window"),
    (ActionId::NewTab, "New Tab"),
    (ActionId::SplitHorizontal, "Split Horizontally"),
    (ActionId::SplitVertical, "Split Vertically"),
    (ActionId::Settings, "Settings"),
    (ActionId::Close, "Close"),
];

fn main() -> gtk4::glib::ExitCode {
    let app = Application::builder()
        .application_id("dev.gnome.Terminator2")
        .flags(gio::ApplicationFlags::empty())
        .build();

    let workspace = Rc::new(RefCell::new(WorkspaceModel::new_single_terminal()));

    let workspace_activate = workspace.clone();
    app.connect_activate(move |app| {
        apply_keybindings(app, &workspace_activate.borrow().keybindings);
        let window_ids: Vec<WindowId> = {
            let ws = workspace_activate.borrow();
            ws.windows.iter().map(|w| w.id).collect()
        };
        if window_ids.is_empty() {
            let id = workspace_activate.borrow_mut().add_window();
            open_window(app, workspace_activate.clone(), id);
        } else {
            for id in window_ids {
                open_window(app, workspace_activate.clone(), id);
            }
        }
    });

    app.run()
}

fn open_window(app: &Application, workspace: Rc<RefCell<WorkspaceModel>>, window_id: WindowId) {
    let (window_title, tab_model) = {
        let ws = workspace.borrow();
        let window_model = ws
            .windows
            .iter()
            .find(|w| w.id == window_id)
            .expect("workspace must contain specified window");
        (
            window_model.title.clone(),
            window_model.active_tab().clone(),
        )
    };

    let tab_title = tab_model.title.clone();
    let flexible_title = tab_model.title_flexible;
    let tab_id = tab_model.id;

    let window = ApplicationWindow::builder()
        .application(app)
        .title(window_title.clone())
        .default_width(960)
        .default_height(540)
        .build();

    let title_text = format!("{} — {}", window_title, tab_title);
    let title_bar = EditableTitleBar::new(title_text, window_title.clone());
    title_bar.set_flexible(flexible_title);

    let terminal = Terminal::new();
    terminal.set_hexpand(true);
    terminal.set_vexpand(true);

    attach_terminal_handlers(
        &terminal,
        title_bar.clone(),
        window.clone(),
        window_title.clone(),
        flexible_title,
    );
    spawn_shell(&terminal);
    install_terminal_menu(&terminal, &window, workspace.clone(), app);

    let container = Box::new(Orientation::Vertical, 0);
    container.append(&terminal);

    let title_widget = title_bar.widget();
    let headerbar = gtk4::HeaderBar::builder().show_title_buttons(true).build();
    headerbar.set_title_widget(Some(&title_widget));
    window.set_titlebar(Some(&headerbar));
    window.set_child(Some(&container));

    connect_title_commit(&workspace, tab_id, &title_bar);

    let workspace_close = workspace.clone();
    window.connect_close_request(move |_win| {
        workspace_close.borrow_mut().remove_window(window_id);
        glib::Propagation::Proceed
    });

    window.present();
}

fn connect_title_commit(
    state: &Rc<RefCell<WorkspaceModel>>,
    tab_id: TabId,
    title_bar: &EditableTitleBar,
) {
    let state_for_commit = Rc::clone(state);
    title_bar.connect_committed(move |is_custom, new_title| {
        let mut state = state_for_commit.borrow_mut();
        if let Some(window) = state.windows.first_mut() {
            if let Some(tab) = window.tabs.iter_mut().find(|t| t.id == tab_id) {
                tab.title = new_title.clone();
                tab.title_flexible = !is_custom;
            }
        }
    });
}

fn attach_terminal_handlers(
    terminal: &Terminal,
    title_bar: EditableTitleBar,
    window: ApplicationWindow,
    window_title: String,
    flexible_title: bool,
) {
    title_bar.update_dynamic(None);

    let weak_window = window.downgrade();

    terminal.connect_window_title_notify(move |term| {
        let mut display_title = term.window_title().map(|s| s.to_string());
        if flexible_title {
            if let Some(dir_uri) = term.current_directory_uri() {
                if let Some(path) = gio::File::for_uri(&dir_uri).path() {
                    let dir = path.display().to_string();
                    if let Some(title) = display_title.as_mut() {
                        *title = format!("{} ({})", title.trim(), dir);
                    } else {
                        display_title = Some(dir);
                    }
                }
            }
        }
        let fallback = display_title.as_deref().unwrap_or(&window_title);
        title_bar.update_dynamic(Some(fallback));
    });

    terminal.connect_child_exited(move |_, _| {
        if let Some(window) = weak_window.upgrade() {
            window.close();
        }
    });
}

fn install_terminal_menu(
    terminal: &Terminal,
    window: &ApplicationWindow,
    workspace: Rc<RefCell<WorkspaceModel>>,
    app: &Application,
) {
    let action_group = gio::SimpleActionGroup::new();

    let term_for_copy = terminal.clone();
    let copy = gio::SimpleAction::new("copy", None);
    copy.connect_activate(move |_, _| {
        term_for_copy.copy_clipboard_format(Format::Text);
    });
    action_group.add_action(&copy);

    let term_for_paste = terminal.clone();
    let paste = gio::SimpleAction::new("paste", None);
    paste.connect_activate(move |_, _| {
        term_for_paste.paste_clipboard();
    });
    action_group.add_action(&paste);

    let app_for_new = app.clone();
    let workspace_for_new = workspace.clone();
    let new_window = gio::SimpleAction::new("new_window", None);
    new_window.connect_activate(move |_, _| {
        create_workspace_window(&app_for_new, workspace_for_new.clone());
    });
    action_group.add_action(&new_window);

    let new_tab = gio::SimpleAction::new("new_tab", None);
    new_tab.connect_activate(|_, _| {
        println!("New tab requested (not yet implemented)");
    });
    action_group.add_action(&new_tab);

    let split_h = gio::SimpleAction::new("split_h", None);
    split_h.connect_activate(|_, _| {
        println!("Horizontal split requested (not yet implemented)");
    });
    action_group.add_action(&split_h);

    let split_v = gio::SimpleAction::new("split_v", None);
    split_v.connect_activate(|_, _| {
        println!("Vertical split requested (not yet implemented)");
    });
    action_group.add_action(&split_v);

    let window_for_close = window.clone();
    let close = gio::SimpleAction::new("close", None);
    close.connect_activate(move |_, _| {
        window_for_close.close();
    });
    action_group.add_action(&close);

    let app_for_settings = app.clone();
    let workspace_for_settings = workspace.clone();
    let window_for_settings = window.clone();
    let settings = gio::SimpleAction::new("settings", None);
    settings.connect_activate(move |_, _| {
        open_settings_dialog(
            &app_for_settings,
            workspace_for_settings.clone(),
            &window_for_settings,
        );
    });
    action_group.add_action(&settings);

    window.insert_action_group("term", Some(&action_group));

    let workspace_for_menu = workspace.clone();
    let terminal_widget = terminal.clone();
    let gesture = GestureClick::new();
    gesture.set_button(3);
    gesture.connect_pressed(move |gesture, _, x, y| {
        let bindings = workspace_for_menu.borrow().keybindings.clone();
        let menu = build_context_menu(&bindings);
        let popover = PopoverMenu::from_model(Some(&menu));
        popover.set_has_arrow(false);
        popover.set_parent(&terminal_widget);
        popover.set_pointing_to(Some(&gdk::Rectangle::new(x as i32, y as i32, 1, 1)));
        popover.set_size_request(-1, 300);
        popover.popup();
        gesture.set_state(gtk4::EventSequenceState::Claimed);
    });
    terminal.add_controller(gesture);
}

fn build_context_menu(bindings: &KeybindingMap) -> gio::Menu {
    use ActionId::*;

    let menu = gio::Menu::new();

    let primary = gio::Menu::new();
    primary.append_item(&menu_item(Copy, "term.copy", bindings));
    primary.append_item(&menu_item(Paste, "term.paste", bindings));

    let layout = gio::Menu::new();
    layout.append_item(&menu_item(NewWindow, "term.new_window", bindings));
    layout.append_item(&menu_item(NewTab, "term.new_tab", bindings));
    layout.append_item(&menu_item(SplitHorizontal, "term.split_h", bindings));
    layout.append_item(&menu_item(SplitVertical, "term.split_v", bindings));

    let secondary = gio::Menu::new();
    secondary.append_item(&menu_item(Settings, "term.settings", bindings));
    secondary.append_item(&menu_item(Close, "term.close", bindings));

    menu.append_section(None, &primary);
    menu.append_section(None, &layout);
    menu.append_section(None, &secondary);

    menu
}

fn menu_item(action: ActionId, detailed: &str, bindings: &KeybindingMap) -> gio::MenuItem {
    let item = gio::MenuItem::new(Some(action_label(action)), Some(detailed));
    if let Some(accels) = bindings.get(&action) {
        if let Some(accel) = accels.first() {
            item.set_attribute_value("accel", Some(&glib::Variant::from(accel.as_str())));
        }
    }
    item
}

fn spawn_shell(terminal: &Terminal) {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| String::from("/bin/sh"));
    let argv = [shell.as_str()];

    let future = terminal.spawn_future(
        PtyFlags::DEFAULT,
        None,
        &argv,
        &[],
        glib::SpawnFlags::SEARCH_PATH,
        || {},
        -1,
    );

    glib::MainContext::default().spawn_local(async move {
        if let Err(error) = future.await {
            eprintln!("Failed to spawn shell: {error}");
        }
    });
}

fn create_workspace_window(app: &Application, workspace: Rc<RefCell<WorkspaceModel>>) -> WindowId {
    let id = workspace.borrow_mut().add_window();
    apply_keybindings(app, &workspace.borrow().keybindings);
    open_window(app, workspace, id);
    id
}

#[allow(deprecated)]
fn open_settings_dialog(
    app: &Application,
    workspace: Rc<RefCell<WorkspaceModel>>,
    parent: &ApplicationWindow,
) {
    let dialog = Dialog::builder()
        .title("Keyboard Shortcuts")
        .transient_for(parent)
        .modal(true)
        .default_width(420)
        .default_height(360)
        .build();
    dialog.add_button("Cancel", ResponseType::Cancel);
    dialog.add_button("Save", ResponseType::Ok);

    let content = dialog.content_area();
    let list = ListBox::new();
    list.set_selection_mode(gtk4::SelectionMode::None);

    let bindings = workspace.borrow().keybindings.clone();
    let mut editors: Vec<(ActionId, Entry)> = Vec::new();

    for (action, label_text) in ACTION_DEFS.iter() {
        let row = ListBoxRow::new();
        let row_box = Box::new(Orientation::Horizontal, 12);
        let label = Label::new(Some(label_text));
        label.set_xalign(0.0);
        label.set_hexpand(true);
        let entry = Entry::new();
        if let Some(accels) = bindings.get(action) {
            if let Some(accel) = accels.first() {
                entry.set_text(accel);
            }
        }
        entry.set_placeholder_text(Some("<Ctrl><Shift>T"));
        row_box.append(&label);
        row_box.append(&entry);
        row.set_child(Some(&row_box));
        list.append(&row);
        editors.push((*action, entry));
    }

    content.append(&list);

    let editors = Rc::new(editors);
    let workspace_store = workspace.clone();
    let app_clone = app.clone();
    dialog.connect_response(move |dialog, response| {
        if response == ResponseType::Ok {
            let mut new_bindings = workspace_store.borrow().keybindings.clone();
            let mut valid = true;
            for (action, entry) in editors.iter() {
                let text = entry.text().trim().to_string();
                if text.is_empty() {
                    entry.remove_css_class("error");
                    new_bindings.insert(*action, Vec::new());
                    continue;
                }
                if let Some((key, mods)) = gtk4::accelerator_parse(&text) {
                    entry.remove_css_class("error");
                    let normalized = gtk4::accelerator_name(key, mods);
                    new_bindings.insert(*action, vec![normalized.to_string()]);
                } else {
                    entry.add_css_class("error");
                    valid = false;
                }
            }
            if valid {
                workspace_store.borrow_mut().keybindings = new_bindings.clone();
                apply_keybindings(&app_clone, &new_bindings);
                dialog.close();
            }
        } else {
            dialog.close();
        }
    });

    dialog.show();
}

fn apply_keybindings(app: &Application, bindings: &KeybindingMap) {
    for action in ACTION_DEFS.iter().map(|(id, _)| *id) {
        let name = action_name(action);
        if let Some(accels) = bindings.get(&action) {
            let refs: Vec<&str> = accels.iter().map(|s| s.as_str()).collect();
            app.set_accels_for_action(name, &refs);
        } else {
            app.set_accels_for_action(name, &[]);
        }
    }
}

fn action_name(action: ActionId) -> &'static str {
    use ActionId::*;
    match action {
        Copy => "term.copy",
        Paste => "term.paste",
        NewWindow => "term.new_window",
        NewTab => "term.new_tab",
        SplitHorizontal => "term.split_h",
        SplitVertical => "term.split_v",
        Settings => "term.settings",
        Close => "term.close",
    }
}

fn action_label(action: ActionId) -> &'static str {
    ACTION_DEFS
        .iter()
        .find(|(id, _)| *id == action)
        .map(|(_, label)| *label)
        .unwrap_or("")
}
