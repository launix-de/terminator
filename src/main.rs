mod model;
mod ui;

use crate::model::{TabId, WorkspaceModel};
use gtk4::{
    Application, ApplicationWindow, Box, GestureClick, Orientation, PopoverMenu, gdk, gio, glib,
    prelude::*,
};
use std::{cell::RefCell, rc::Rc};
use ui::EditableTitleBar;
use vte4::{Format, PtyFlags, Terminal, prelude::*};

fn main() -> gtk4::glib::ExitCode {
    let app = Application::builder()
        .application_id("dev.gnome.Terminator2")
        .flags(gio::ApplicationFlags::empty())
        .build();

    let state = WorkspaceModel::new_single_terminal();
    let workspace = Rc::new(RefCell::new(state));

    app.connect_activate(move |app| build_ui(app, workspace.clone()));

    app.run()
}

fn build_ui(app: &Application, state: Rc<RefCell<WorkspaceModel>>) {
    let state_ref = state.borrow();
    let window_model = state_ref
        .windows
        .first()
        .expect("workspace must contain at least one window");
    let tab_model = window_model.active_tab();
    let tab_title = tab_model.title.clone();
    let window_title = window_model.title.clone();
    let _terminal_id = tab_model.active_terminal();
    let flexible_title = tab_model.title_flexible;
    let tab_id = tab_model.id;
    drop(state_ref);

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
    install_terminal_menu(&terminal, &window);

    let container = Box::new(Orientation::Vertical, 0);
    container.append(&terminal);

    let title_widget = title_bar.widget();
    let headerbar = gtk4::HeaderBar::builder().show_title_buttons(true).build();
    headerbar.set_title_widget(Some(&title_widget));
    window.set_titlebar(Some(&headerbar));
    window.set_child(Some(&container));

    connect_title_commit(&state, tab_id, &title_bar);

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

fn install_terminal_menu(terminal: &Terminal, window: &ApplicationWindow) {
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

    let win_for_close = window.clone();
    let close = gio::SimpleAction::new("close", None);
    close.connect_activate(move |_, _| {
        win_for_close.close();
    });
    action_group.add_action(&close);

    let settings = gio::SimpleAction::new("settings", None);
    settings.connect_activate(|_, _| {
        println!("Settings requested (not yet implemented)");
    });
    action_group.add_action(&settings);

    window.insert_action_group("term", Some(&action_group));

    let menu = gio::Menu::new();
    let section_primary = gio::Menu::new();
    section_primary.append(Some("Copy"), Some("term.copy"));
    section_primary.append(Some("Paste"), Some("term.paste"));

    let section_layout = gio::Menu::new();
    section_layout.append(Some("New Tab"), Some("term.new_tab"));
    section_layout.append(Some("Split Horizontally"), Some("term.split_h"));
    section_layout.append(Some("Split Vertically"), Some("term.split_v"));

    let section_secondary = gio::Menu::new();
    section_secondary.append(Some("Settings"), Some("term.settings"));
    section_secondary.append(Some("Close"), Some("term.close"));

    menu.append_section(None, &section_primary);
    menu.append_section(None, &section_layout);
    menu.append_section(None, &section_secondary);

    let popover = PopoverMenu::from_model(Some(&menu));
    popover.set_has_arrow(false);
    popover.set_parent(&terminal.clone());

    let popover_clone = popover.clone();
    let gesture = GestureClick::new();
    gesture.set_button(3);
    gesture.connect_pressed(move |_gesture, _, x, y| {
        popover_clone.set_pointing_to(Some(&gdk::Rectangle::new(x as i32, y as i32, 1, 1)));
        popover_clone.popup();
    });
    terminal.add_controller(gesture);
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
