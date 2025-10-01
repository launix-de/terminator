mod model;
mod ui;

use crate::model::{
    ActionId, InnerTabId, KeybindingMap, LayoutNode, SplitNode, SplitOrientation, TabGroup, TabId,
    TerminalId, TerminalLeaf, WindowId, WindowModel, WorkspaceModel,
};
use crate::ui::{EditableTabLabel, EditableTitleBar};
use glib::signal::{signal_handler_block, signal_handler_unblock};
use gtk4::{
    Application, ApplicationWindow, Box, Button, Dialog, Entry, EventControllerFocus, GestureClick,
    HeaderBar, Image, Label, ListBox, ListBoxRow, Notebook, Orientation, Paned, PopoverMenu,
    ResponseType, StyleContext,
    gdk::{RGBA, Rectangle},
    gio, glib,
    prelude::*,
};
use std::cell::{Cell, RefCell};
use std::collections::{HashMap, HashSet};
use std::rc::{Rc, Weak};

thread_local! {
    static CUSTOM_CSS_PROVIDER: RefCell<Option<gtk4::CssProvider>> = RefCell::new(None);
}
use vte4::{Format, PtyFlags, Terminal, prelude::*};

const ACTION_DEFS: &[(ActionId, &str)] = &[
    (ActionId::Copy, "Copy"),
    (ActionId::Paste, "Paste"),
    (ActionId::NewWindow, "New Window"),
    (ActionId::NewTab, "New Tab"),
    (ActionId::NewInnerTab, "New Inner Tab"),
    (ActionId::SplitHorizontal, "Split Horizontally"),
    (ActionId::SplitVertical, "Split Vertically"),
    (ActionId::Settings, "Settings"),
    (ActionId::Close, "Close"),
    (ActionId::CloseInnerTab, "Close Inner Tab"),
];

fn main() -> gtk4::glib::ExitCode {
    let app = Application::builder()
        .application_id("dev.gnome.Terminator2")
        .flags(gio::ApplicationFlags::empty())
        .build();

    ensure_custom_css();

    let workspace = Rc::new(RefCell::new(WorkspaceModel::new_single_terminal()));
    let app_clone = app.clone();
    let workspace_clone = workspace.clone();

    let state = Rc::new_cyclic(|weak| AppState {
        app: app_clone.clone(),
        workspace: workspace_clone.clone(),
        registry: RefCell::new(TerminalRegistry::new(weak.clone())),
        controllers: RefCell::new(HashMap::new()),
        last_focus: RefCell::new(HashMap::new()),
        creating_op: Cell::new(false),
    });

    state.install_theme_listener();

    let state_activate = state.clone();
    app.connect_activate(move |app| {
        state_activate.on_activate(app);
    });

    app.run()
}

struct AppState {
    app: Application,
    workspace: Rc<RefCell<WorkspaceModel>>,
    registry: RefCell<TerminalRegistry>,
    controllers: RefCell<HashMap<WindowId, Rc<WorkspaceController>>>,
    last_focus: RefCell<HashMap<WindowId, (TabId, TerminalId)>>,
    creating_op: Cell<bool>,
}

impl AppState {
    fn on_activate(self: &Rc<Self>, app: &Application) {
        apply_keybindings(app, &self.workspace.borrow().keybindings);

        let window_ids: Vec<WindowId> = {
            let ws = self.workspace.borrow();
            ws.windows.iter().map(|w| w.id).collect()
        };

        if window_ids.is_empty() {
            let id = self.workspace.borrow_mut().add_window();
            self.ensure_window(id);
        } else {
            for id in window_ids {
                self.ensure_window(id);
            }
        }
    }

    fn ensure_window(self: &Rc<Self>, window_id: WindowId) {
        if self.controllers.borrow().contains_key(&window_id) {
            return;
        }

        let controller = WorkspaceController::new(self.clone(), window_id);
        let initial_focus = controller.current_tab_id().and_then(|tab_id| {
            let term = self
                .workspace
                .borrow()
                .first_terminal_in_tab(window_id, tab_id);
            term.map(|term_id| (tab_id, term_id))
        });

        self.controllers.borrow_mut().insert(window_id, controller);

        if let Some((tab_id, term_id)) = initial_focus {
            let weak = Rc::downgrade(self);
            glib::idle_add_local(move || {
                if let Some(state) = weak.upgrade() {
                    state.focus_and_remember(window_id, tab_id, term_id);
                }
                glib::ControlFlow::Break
            });
        }
    }

    fn create_window(self: &Rc<Self>) -> WindowId {
        let id = self.workspace.borrow_mut().add_window();
        self.ensure_window(id);
        apply_keybindings(&self.app, &self.workspace.borrow().keybindings);
        id
    }

    fn close_terminal(self: &Rc<Self>, window_id: WindowId, terminal_id: TerminalId) {
        let removed = self
            .workspace
            .borrow_mut()
            .close_terminal(window_id, terminal_id)
            .is_some();
        if !removed {
            return;
        }

        {
            let mut registry = self.registry.borrow_mut();
            registry.remove_terminal(terminal_id);
        }

        self.last_focus.borrow_mut().remove(&window_id);

        if self
            .workspace
            .borrow()
            .windows
            .iter()
            .any(|w| w.id == window_id)
        {
            self.rebuild_window(window_id);
        } else {
            let controller = {
                let mut controllers = self.controllers.borrow_mut();
                controllers.remove(&window_id)
            };
            if let Some(controller) = controller {
                controller.close_window();
            }
        }
    }

    fn rebuild_window(self: &Rc<Self>, window_id: WindowId) {
        if let Some(controller) = self.controllers.borrow().get(&window_id) {
            controller.rebuild();
        }
    }

    fn handle_terminal_exit(self: &Rc<Self>, terminal_id: TerminalId) {
        let window_id = {
            let registry = self.registry.borrow();
            registry.window_for_terminal(terminal_id)
        };
        if let Some(window_id) = window_id {
            self.close_terminal(window_id, terminal_id);
        }
    }

    fn current_tab_id(&self, window_id: WindowId) -> Option<TabId> {
        let ws = self.workspace.borrow();
        ws.windows
            .iter()
            .find(|w| w.id == window_id)
            .map(|window| window.active_tab().id)
    }

    fn split_active(self: &Rc<Self>, window_id: WindowId, orientation: SplitOrientation) {
        let current_tab = self.current_tab_id(window_id);
        let focused = {
            if let Some((tab, term)) = self.last_focus.borrow().get(&window_id) {
                if Some(*tab) == current_tab {
                    Some(*term)
                } else {
                    None
                }
            } else {
                None
            }
        }
        .or_else(|| {
            let ws = self.workspace.borrow();
            ws.windows
                .iter()
                .find(|w| w.id == window_id)
                .map(|window| window.active_tab().active_terminal())
        });

        if let Some(terminal_id) = focused {
            let new_terminal =
                self.workspace
                    .borrow_mut()
                    .split_terminal(window_id, terminal_id, orientation);
            if let Some(new_id) = new_terminal {
                self.registry.borrow_mut().ensure_terminal(new_id);
                let tab_id = current_tab.or_else(|| self.current_tab_id(window_id));
                self.rebuild_window(window_id);
                if let Some(tab_id) = tab_id {
                    let weak = Rc::downgrade(self);
                    glib::idle_add_local(move || {
                        if let Some(app_state) = weak.upgrade() {
                            app_state.focus_and_remember(window_id, tab_id, new_id);
                        }
                        glib::ControlFlow::Break
                    });
                }
            }
        }
    }

    fn new_tab(self: &Rc<Self>, window_id: WindowId) {
        if self.creating_op.replace(true) {
            return;
        }
        if let Some(new_tab) = self.workspace.borrow_mut().add_tab_to_window(window_id) {
            let weak = Rc::downgrade(self);
            glib::idle_add_local(move || {
                if let Some(app_state) = weak.upgrade() {
                    app_state.rebuild_window(window_id);
                    if let Some(term_id) = {
                        let ws = app_state.workspace.borrow();
                        ws.first_terminal_in_tab(window_id, new_tab)
                    } {
                        app_state.focus_and_remember(window_id, new_tab, term_id);
                    }
                    app_state.creating_op.set(false);
                }
                glib::ControlFlow::Break
            });
        } else {
            self.creating_op.set(false);
        }
    }

    fn new_inner_tab(self: &Rc<Self>, window_id: WindowId) {
        if self.creating_op.replace(true) {
            return;
        }
        let current_tab = self.current_tab_id(window_id);
        let focused_terminal = {
            let ws = self.workspace.borrow();
            ws.windows
                .iter()
                .find(|w| w.id == window_id)
                .map(|window| window.active_tab().active_terminal())
        };
        if let (Some(tab_id), Some(from_terminal)) = (current_tab, focused_terminal) {
            if let Some((_inner_id, new_terminal)) = self
                .workspace
                .borrow_mut()
                .add_inner_tab(window_id, tab_id, from_terminal)
            {
                self.registry.borrow_mut().ensure_terminal(new_terminal);
                let weak = Rc::downgrade(self);
                glib::idle_add_local(move || {
                    if let Some(state) = weak.upgrade() {
                        state.rebuild_window(window_id);
                        state.focus_and_remember(window_id, tab_id, new_terminal);
                        state.creating_op.set(false);
                    }
                    glib::ControlFlow::Break
                });
            } else {
                self.creating_op.set(false);
            }
        } else {
            self.creating_op.set(false);
        }
    }

    fn close_inner_tab(
        self: &Rc<Self>,
        window_id: WindowId,
        tab_id: TabId,
        inner_id: InnerTabId,
    ) {
        let changed = self
            .workspace
            .borrow_mut()
            .close_inner_tab(window_id, tab_id, inner_id);
        if changed {
            let weak = Rc::downgrade(self);
            glib::idle_add_local(move || {
                if let Some(state) = weak.upgrade() {
                    state.rebuild_window(window_id);
                    if let Some(term_id) = {
                        let ws = state.workspace.borrow();
                        ws.first_terminal_in_tab(window_id, tab_id)
                    } {
                        state.focus_and_remember(window_id, tab_id, term_id);
                    }
                }
                glib::ControlFlow::Break
            });
        }
    }

    fn rename_tab(
        self: &Rc<Self>,
        window_id: WindowId,
        tab_id: TabId,
        title: String,
        flexible: bool,
    ) -> bool {
        let changed = self
            .workspace
            .borrow_mut()
            .rename_tab(window_id, tab_id, title, flexible);
        if changed {
            let weak = Rc::downgrade(self);
            glib::idle_add_local(move || {
                if let Some(controller) = weak.upgrade() {
                    controller.rebuild_window(window_id);
                }
                glib::ControlFlow::Break
            });
        }
        changed
    }

    fn rename_inner_tab(
        self: &Rc<Self>,
        window_id: WindowId,
        tab_id: TabId,
        inner_id: InnerTabId,
        title: String,
        flexible: bool,
    ) -> bool {
        let changed = self
            .workspace
            .borrow_mut()
            .rename_inner_tab(window_id, tab_id, inner_id, title, flexible);
        if changed {
            let weak = Rc::downgrade(self);
            glib::idle_add_local(move || {
                if let Some(controller) = weak.upgrade() {
                    controller.rebuild_window(window_id);
                }
                glib::ControlFlow::Break
            });
        }
        changed
    }

    fn close_active(self: &Rc<Self>, window_id: WindowId) {
        let active_terminal = {
            let ws = self.workspace.borrow();
            ws.windows
                .iter()
                .find(|w| w.id == window_id)
                .map(|window| window.active_tab().active_terminal())
        };
        if let Some(terminal_id) = active_terminal {
            self.close_terminal(window_id, terminal_id);
        }
    }

    fn set_active_tab(self: &Rc<Self>, window_id: WindowId, tab_id: TabId) {
        let already_active = {
            let ws = self.workspace.borrow();
            ws.windows
                .iter()
                .find(|w| w.id == window_id)
                .and_then(|window| {
                    window
                        .tabs
                        .iter()
                        .position(|tab| tab.id == tab_id)
                        .map(|idx| idx == window.active_tab)
                })
                .unwrap_or(false)
        };
        if already_active {
            return;
        }

        self.workspace
            .borrow_mut()
            .set_active_tab(window_id, tab_id);

        let first_terminal = {
            let ws = self.workspace.borrow();
            ws.first_terminal_in_tab(window_id, tab_id)
        };

        let weak = Rc::downgrade(self);
        glib::idle_add_local(move || {
            if let Some(app_state) = weak.upgrade() {
                app_state.rebuild_window(window_id);
                if let Some(term_id) = first_terminal {
                    app_state.focus_and_remember(window_id, tab_id, term_id);
                }
            }
            glib::ControlFlow::Break
        });
    }

    fn set_active_terminal(
        self: &Rc<Self>,
        window_id: WindowId,
        tab_id: TabId,
        terminal: TerminalId,
    ) {
        let changed = self
            .workspace
            .borrow_mut()
            .set_active_terminal(window_id, tab_id, terminal);
        if changed {
            self.last_focus
                .borrow_mut()
                .insert(window_id, (tab_id, terminal));

            let weak = Rc::downgrade(self);
            glib::idle_add_local(move || {
                if let Some(app_state) = weak.upgrade() {
                    app_state.rebuild_window(window_id);
                    app_state.focus_and_remember(window_id, tab_id, terminal);
                }
                glib::ControlFlow::Break
            });
        }
    }

    fn apply_settings(&self, bindings: KeybindingMap) {
        self.workspace.borrow_mut().keybindings = bindings.clone();
        apply_keybindings(&self.app, &bindings);
    }

    #[allow(deprecated)]
    fn open_settings_dialog(self: &Rc<Self>, parent: &ApplicationWindow) {
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

        let bindings = self.workspace.borrow().keybindings.clone();
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
        let state = self.clone();
        let dialog_clone = dialog.clone();
        dialog.connect_response(move |dialog, response| {
            if response == ResponseType::Ok {
                let mut new_bindings = state.workspace.borrow().keybindings.clone();
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
                    state.apply_settings(new_bindings);
                    dialog.close();
                }
            } else {
                dialog.close();
            }
        });

        dialog_clone.show();
    }

    fn registry(&self) -> &RefCell<TerminalRegistry> {
        &self.registry
    }

    fn install_theme_listener(self: &Rc<Self>) {
        if let Some(display) = gtk4::gdk::Display::default() {
            let settings = gtk4::Settings::for_display(&display);
            let weak = Rc::downgrade(self);
            settings.connect_gtk_theme_name_notify(move |_| {
                if let Some(state) = weak.upgrade() {
                    state.registry.borrow().reapply_theme();
                }
            });

            let weak = Rc::downgrade(self);
            settings.connect_gtk_application_prefer_dark_theme_notify(move |_| {
                if let Some(state) = weak.upgrade() {
                    state.registry.borrow().reapply_theme();
                }
            });
        }
    }

    fn focus_and_remember(&self, window_id: WindowId, tab_id: TabId, terminal_id: TerminalId) {
        let controller = {
            let controllers_ref = self.controllers.borrow();
            controllers_ref.get(&window_id).cloned()
        };
        if let Some(controller) = controller {
            controller.focus_terminal(terminal_id);
        }
        self.last_focus
            .borrow_mut()
            .insert(window_id, (tab_id, terminal_id));
    }
}

struct WorkspaceController {
    state: Weak<AppState>,
    window_id: WindowId,
    window: ApplicationWindow,
    title_bar: EditableTitleBar,
    notebook: Notebook,
    page_tab_ids: RefCell<Vec<TabId>>,
    title_handler: RefCell<Option<(Terminal, glib::SignalHandlerId, glib::SignalHandlerId)>>,
    switch_handler: RefCell<Option<glib::SignalHandlerId>>,
    tab_labels: RefCell<HashMap<TabId, EditableTabLabel>>,
    inner_tab_labels: RefCell<HashMap<InnerTabId, EditableTabLabel>>,
    suppress_focus: Cell<bool>,
}

impl WorkspaceController {
    fn new(state: Rc<AppState>, window_id: WindowId) -> Rc<Self> {
        let window_model = {
            let ws = state.workspace.borrow();
            ws.windows
                .iter()
                .find(|w| w.id == window_id)
                .cloned()
                .expect("window must exist")
        };

        let active_tab = window_model.active_tab();
        let title_text = format!("{} — {}", window_model.title, active_tab.display_title());
        let title_bar = EditableTitleBar::new(title_text.clone(), window_model.title.clone());
        title_bar.set_flexible(active_tab.is_title_flexible());

        let window = ApplicationWindow::builder()
            .application(&state.app)
            .title(window_model.title.clone())
            .default_width(960)
            .default_height(540)
            .build();

        let header = HeaderBar::builder().show_title_buttons(true).build();
        header.set_title_widget(Some(&title_bar.widget()));
        window.set_titlebar(Some(&header));

        let container = Box::new(Orientation::Vertical, 0);
        container.set_hexpand(true);
        container.set_vexpand(true);

        let notebook = Notebook::new();
        notebook.set_hexpand(true);
        notebook.set_vexpand(true);
        notebook.set_scrollable(true);
        container.append(&notebook);
        window.set_child(Some(&container));

        window.present();

        let controller = Rc::new_cyclic(|_weak| WorkspaceController {
            state: Rc::downgrade(&state),
            window_id,
            window: window.clone(),
            title_bar: title_bar.clone(),
            notebook: notebook.clone(),
            page_tab_ids: RefCell::new(Vec::new()),
            title_handler: RefCell::new(None),
            switch_handler: RefCell::new(None),
            tab_labels: RefCell::new(HashMap::new()),
            inner_tab_labels: RefCell::new(HashMap::new()),
            suppress_focus: Cell::new(false),
        });

        controller.install_actions();
        controller.setup_callbacks();
        controller.rebuild();

        controller
    }

    fn install_actions(self: &Rc<Self>) {
        let action_group = gio::SimpleActionGroup::new();
        let weak_self = Rc::downgrade(self);

        let copy = gio::SimpleAction::new("copy", None);
        copy.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                controller.copy_active();
            }
        });
        action_group.add_action(&copy);

        let weak_self = Rc::downgrade(self);
        let paste = gio::SimpleAction::new("paste", None);
        paste.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                controller.paste_active();
            }
        });
        action_group.add_action(&paste);

        let weak_self = Rc::downgrade(self);
        let new_window = gio::SimpleAction::new("new_window", None);
        new_window.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state.create_window();
                }
            }
        });
        action_group.add_action(&new_window);

        let weak_self = Rc::downgrade(self);
        let new_tab = gio::SimpleAction::new("new_tab", None);
        new_tab.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state.new_tab(controller.window_id);
                }
            }
        });
        action_group.add_action(&new_tab);

        let weak_self = Rc::downgrade(self);
        let split_h = gio::SimpleAction::new("split_h", None);
        split_h.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state.split_active(controller.window_id, SplitOrientation::Horizontal);
                }
            }
        });
        action_group.add_action(&split_h);

        let weak_self = Rc::downgrade(self);
        let split_v = gio::SimpleAction::new("split_v", None);
        split_v.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state.split_active(controller.window_id, SplitOrientation::Vertical);
                }
            }
        });
        action_group.add_action(&split_v);

        let weak_self = Rc::downgrade(self);
        let new_inner_tab = gio::SimpleAction::new("new_inner_tab", None);
        new_inner_tab.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state.new_inner_tab(controller.window_id);
                }
            }
        });
        action_group.add_action(&new_inner_tab);

        let weak_self = Rc::downgrade(self);
        let close_inner_tab = gio::SimpleAction::new("close_inner_tab", None);
        close_inner_tab.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    if let Some(tab_id) = state.current_tab_id(controller.window_id) {
                        if let Some(inner_id) = {
                            let ws = state.workspace.borrow();
                            ws.windows
                                .iter()
                                .find(|w| w.id == controller.window_id)
                                .and_then(|window| window.tabs.iter().find(|t| t.id == tab_id))
                                .and_then(|tab| match &tab.root {
                                    LayoutNode::Tabs(group) => group.tabs.get(group.active).map(|i| i.id),
                                    _ => None,
                                })
                        } {
                            state.close_inner_tab(controller.window_id, tab_id, inner_id);
                        }
                    }
                }
            }
        });
        action_group.add_action(&close_inner_tab);

        let weak_self = Rc::downgrade(self);
        let close = gio::SimpleAction::new("close", None);
        close.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state.close_active(controller.window_id);
                }
            }
        });
        action_group.add_action(&close);

        let weak_self = Rc::downgrade(self);
        let settings = gio::SimpleAction::new("settings", None);
        settings.connect_activate(move |_, _| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state.open_settings_dialog(&controller.window);
                }
            }
        });
        action_group.add_action(&settings);

        self.window.insert_action_group("term", Some(&action_group));
    }

    fn setup_callbacks(self: &Rc<Self>) {
        let weak_self = Rc::downgrade(self);
        self.window.connect_close_request(move |_| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    state
                        .workspace
                        .borrow_mut()
                        .remove_window(controller.window_id);
                    state.controllers.borrow_mut().remove(&controller.window_id);
                    state
                        .registry()
                        .borrow_mut()
                        .cleanup_for_window(controller.window_id, &[]);
                }
            }
            glib::Propagation::Proceed
        });

        let weak_self = Rc::downgrade(self);
        self.title_bar
            .connect_committed(move |is_custom, new_title| {
                if let Some(controller) = weak_self.upgrade() {
                    if let Some(state) = controller.state.upgrade() {
                        let tab_id = {
                            let workspace = state.workspace.borrow();
                            workspace
                                .windows
                                .iter()
                                .find(|w| w.id == controller.window_id)
                                .and_then(|window| window.tabs.get(window.active_tab))
                                .map(|tab| tab.id)
                        };
                        if let Some(tab_id) = tab_id {
                            let flexible = !is_custom;
                            state.rename_tab(
                                controller.window_id,
                                tab_id,
                                new_title.clone(),
                                flexible,
                            );
                        }
                    }
                }
            });

        let weak_self = Rc::downgrade(self);
        let handler = self.notebook.connect_switch_page(move |_, _, index| {
            if let Some(controller) = weak_self.upgrade() {
                if let Some(state) = controller.state.upgrade() {
                    let tab_id = {
                        let ids = controller.page_tab_ids.borrow();
                        ids.get(index as usize).cloned()
                    };
                    if let Some(tab_id) = tab_id {
                        state.set_active_tab(controller.window_id, tab_id);
                    }
                }
            }
        });
        self.switch_handler.borrow_mut().replace(handler);
    }

    fn rebuild(self: &Rc<Self>) {
        let state = match self.state.upgrade() {
            Some(state) => state,
            None => return,
        };

        let window_model = {
            let ws = state.workspace.borrow();
            ws.windows.iter().find(|w| w.id == self.window_id).cloned()
        };

        let Some(window_model) = window_model else {
            self.window.close();
            return;
        };

        self.window.set_title(Some(&window_model.title));

        let active_tab = window_model.active_tab();
        let title_text = format!("{} — {}", window_model.title, active_tab.display_title());
        self.title_bar.set_titles(
            &title_text,
            &window_model.title,
            active_tab.is_title_flexible(),
        );

        if let Some(handler_id) = self.switch_handler.borrow().as_ref() {
            signal_handler_block(&self.notebook, handler_id);
            self.refresh_notebook(window_model.clone());
            self.notebook.set_show_tabs(window_model.tabs.len() > 1);
            // Only adjust current page if it differs to avoid spurious signals
            if self
                .notebook
                .current_page()
                .map(|p| p as usize)
                != Some(window_model.active_tab)
            {
                self.notebook
                    .set_current_page(Some(window_model.active_tab as u32));
            }
            signal_handler_unblock(&self.notebook, handler_id);
        } else {
            self.refresh_notebook(window_model.clone());
            self.notebook.set_show_tabs(window_model.tabs.len() > 1);
            if self
                .notebook
                .current_page()
                .map(|p| p as usize)
                != Some(window_model.active_tab)
            {
                self.notebook
                    .set_current_page(Some(window_model.active_tab as u32));
            }
        }

        let terminal_id = active_tab.active_terminal();
        self.bind_active_terminal(terminal_id, active_tab.is_title_flexible());

        let keep_ids: Vec<TerminalId> = window_model
            .tabs
            .iter()
            .flat_map(|tab| {
                let mut ids = Vec::new();
                tab.collect_terminal_ids(&mut ids);
                ids
            })
            .collect();
        state
            .registry()
            .borrow_mut()
            .cleanup_for_window(self.window_id, &keep_ids);
    }

    fn focus_terminal(&self, terminal_id: TerminalId) {
        if let Some(state) = self.state.upgrade() {
            if let Some(terminal) = state.registry.borrow().terminal(terminal_id) {
                self.suppress_focus.set(true);
                terminal.grab_focus();
            }
        }
    }

    fn build_node(
        self: &Rc<Self>,
        tab_id: TabId,
        node: &LayoutNode,
        from_split: bool,
    ) -> gtk4::Widget {
        match node {
            LayoutNode::Terminal(leaf) => self
                .build_terminal(tab_id, leaf, from_split)
                .upcast::<gtk4::Widget>(),
            LayoutNode::Split(split) => self.build_split(tab_id, split),
            LayoutNode::Tabs(group) => self.build_inner_tabs(tab_id, group),
        }
    }

    fn build_split(self: &Rc<Self>, tab_id: TabId, split: &SplitNode) -> gtk4::Widget {
        let orientation = match split.orientation {
            SplitOrientation::Horizontal => Orientation::Horizontal,
            SplitOrientation::Vertical => Orientation::Vertical,
        };

        let mut children_iter = split.children.iter();
        let first = children_iter
            .next()
            .map(|child| self.build_node(tab_id, child, true))
            .unwrap_or_else(|| Box::new(Orientation::Vertical, 0).upcast());

        children_iter.fold(first, |acc, child| {
            let paned = Paned::new(orientation);
            paned.set_hexpand(true);
            paned.set_vexpand(true);
            paned.set_start_child(Some(&acc));
            let next = self.build_node(tab_id, child, true);
            paned.set_end_child(Some(&next));
            paned.upcast()
        })
    }

    fn build_terminal(
        self: &Rc<Self>,
        tab_id: TabId,
        leaf: &TerminalLeaf,
        show_header: bool,
    ) -> Box {
        let state = match self.state.upgrade() {
            Some(state) => state,
            None => return Box::new(Orientation::Vertical, 0),
        };

        let terminal = {
            let mut registry = state.registry.borrow_mut();
            registry.attach_terminal(leaf.terminal_id, self.window_id, leaf.title_flexible)
        };

        let wrapper = Box::new(Orientation::Vertical, if show_header { 2 } else { 0 });
        wrapper.set_hexpand(true);
        wrapper.set_vexpand(true);

        let mut label_ref: Option<Label> = None;
        if show_header {
            let header = Box::new(Orientation::Horizontal, 4);
            header.add_css_class("terminal-header");
            let label = Label::new(Some("Terminal"));
            label.set_xalign(0.0);
            label.set_halign(gtk4::Align::Start);
            header.append(&label);
            label_ref = Some(label);
            wrapper.append(&header);
        }
        wrapper.append(&terminal);

        if let Some(label) = &label_ref {
            state.registry().borrow_mut().register_label(
                leaf.terminal_id,
                label,
                leaf.title_flexible,
            );
        }

        // Install focus controller only once per terminal
        let already_installed = unsafe { terminal.data::<bool>("focus_installed") }.is_some();
        if !already_installed {
            unsafe { terminal.set_data("focus_installed", true) };
            let focus_controller = EventControllerFocus::new();
            let weak_self = Rc::downgrade(self);
            let focus_tab = tab_id;
            let focus_terminal = leaf.terminal_id;
            focus_controller.connect_enter(move |_| {
                if let Some(controller) = weak_self.upgrade() {
                    if controller.suppress_focus.replace(false) {
                        return;
                    }
                    if let Some(state) = controller.state.upgrade() {
                        state.set_active_terminal(controller.window_id, focus_tab, focus_terminal);
                    }
                }
            });
            terminal.add_controller(focus_controller);
        }

        self.install_terminal_menu(&terminal, tab_id, leaf.terminal_id);

        wrapper
    }

    fn build_inner_tabs(self: &Rc<Self>, tab_id: TabId, group: &TabGroup) -> gtk4::Widget {
        let notebook = Notebook::new();
        notebook.set_hexpand(true);
        notebook.set_vexpand(true);

        for inner in &group.tabs {
            let page = self.build_node(tab_id, &inner.root, false);
            page.set_hexpand(true);
            page.set_vexpand(true);

            let inner_label =
                EditableTabLabel::new(inner.display_title(), inner.is_title_flexible());
            let label_box = Box::new(Orientation::Horizontal, 6);
            let label_widget = inner_label.widget();
            label_box.append(&label_widget);
            let close_btn = Button::new();
            close_btn.add_css_class("flat");
            let img = Image::from_icon_name("window-close-symbolic");
            close_btn.set_child(Some(&img));
            label_box.append(&close_btn);

            let weak_self = Rc::downgrade(self);
            let inner_id = inner.id;
            inner_label.connect_committed(move |is_custom, new_title| {
                if let Some(controller) = weak_self.upgrade() {
                    if let Some(state) = controller.state.upgrade() {
                        let flexible = !is_custom;
                        state.rename_inner_tab(
                            controller.window_id,
                            tab_id,
                            inner_id,
                            new_title.clone(),
                            flexible,
                        );
                    }
                }
            });

            let weak_self = Rc::downgrade(self);
            close_btn.connect_clicked(move |_| {
                if let Some(controller) = weak_self.upgrade() {
                    if let Some(state) = controller.state.upgrade() {
                        state.close_inner_tab(controller.window_id, tab_id, inner_id);
                    }
                }
            });

            self.inner_tab_labels
                .borrow_mut()
                .insert(inner.id, inner_label);

            notebook.append_page(&page, Some(&label_box));
        }

        notebook.set_show_tabs(group.tabs.len() > 1);
        notebook.set_current_page(Some(group.active as u32));

        notebook.upcast()
    }

    fn refresh_notebook(self: &Rc<Self>, window_model: WindowModel) {
        while self.notebook.n_pages() > 0 {
            self.notebook.remove_page(Some(0));
        }

        self.tab_labels.borrow_mut().clear();
        self.inner_tab_labels.borrow_mut().clear();

        let mut new_page_ids = Vec::with_capacity(window_model.tabs.len());

        for tab in &window_model.tabs {
            let page = self.build_node(tab.id, &tab.root, false);
            page.set_hexpand(true);
            page.set_vexpand(true);

            let tab_label = EditableTabLabel::new(tab.display_title(), tab.is_title_flexible());
            let label_widget = tab_label.widget();

            let weak_self = Rc::downgrade(self);
            let tab_id = tab.id;
            tab_label.connect_committed(move |is_custom, new_title| {
                if let Some(controller) = weak_self.upgrade() {
                    if let Some(state) = controller.state.upgrade() {
                        let flexible = !is_custom;
                        state.rename_tab(controller.window_id, tab_id, new_title.clone(), flexible);
                    }
                }
            });

            self.notebook.append_page(&page, Some(&label_widget));
            self.tab_labels.borrow_mut().insert(tab.id, tab_label);
            new_page_ids.push(tab.id);
        }

        *self.page_tab_ids.borrow_mut() = new_page_ids;
    }

    fn current_tab_id(&self) -> Option<TabId> {
        let index = self.notebook.current_page()? as usize;
        self.page_tab_ids.borrow().get(index).copied()
    }

    fn install_terminal_menu(
        self: &Rc<Self>,
        terminal: &Terminal,
        tab_id: TabId,
        terminal_id: TerminalId,
    ) {
        // Install context menu gesture only once per terminal
        let menu_installed = unsafe { terminal.data::<bool>("menu_installed") }.is_some();
        if !menu_installed {
            unsafe { terminal.set_data("menu_installed", true) };
            let gesture = GestureClick::new();
            gesture.set_button(3);
            let weak_self = Rc::downgrade(self);
            let term_clone = terminal.clone();
            // Per-terminal open state to prevent multiple popovers
            let open_state: Rc<Cell<bool>> = Rc::new(Cell::new(false));
            gesture.connect_pressed(move |gesture, _, x, y| {
                if open_state.get() {
                    gesture.set_state(gtk4::EventSequenceState::Claimed);
                    return;
                }
                if let Some(controller) = weak_self.upgrade() {
                    if let Some(state) = controller.state.upgrade() {
                        state.set_active_terminal(controller.window_id, tab_id, terminal_id);
                        let bindings = state.workspace.borrow().keybindings.clone();
                        let menu = build_context_menu(&bindings);
                        let popover = PopoverMenu::from_model(Some(&menu));
                        popover.set_has_arrow(false);
                        popover.set_parent(&term_clone);
                        popover.set_pointing_to(Some(&Rectangle::new(x as i32, y as i32, 1, 1)));
                        popover.set_size_request(-1, 300);
                        open_state.set(true);
                        let open_state_close = open_state.clone();
                        popover.connect_closed(move |_| {
                            open_state_close.set(false);
                        });
                        popover.popup();
                        gesture.set_state(gtk4::EventSequenceState::Claimed);
                    }
                }
            });
            terminal.add_controller(gesture);
        }
    }

    fn bind_active_terminal(self: &Rc<Self>, terminal_id: TerminalId, flexible: bool) {
        if let Some(state) = self.state.upgrade() {
            if let Some(terminal) = state.registry.borrow().terminal(terminal_id) {
                if let Some((prev_terminal, title_handler, dir_handler)) =
                    self.title_handler.borrow_mut().take()
                {
                    prev_terminal.disconnect(title_handler);
                    prev_terminal.disconnect(dir_handler);
                }

                let weak_self = Rc::downgrade(self);
                let terminal_clone = terminal.clone();
                let handler_title = terminal.connect_window_title_notify(move |term| {
                    if let Some(controller) = weak_self.upgrade() {
                        controller.update_title_dynamic(term, flexible);
                    }
                });
                let weak_self = Rc::downgrade(self);
                let handler_dir = terminal.connect_current_directory_uri_notify(move |term| {
                    if let Some(controller) = weak_self.upgrade() {
                        controller.update_title_dynamic(term, flexible);
                    }
                });
                self.title_handler.borrow_mut().replace((
                    terminal_clone,
                    handler_title,
                    handler_dir,
                ));
                self.update_title_dynamic(&terminal, flexible);
            }
        }
    }

    fn update_title_dynamic(&self, terminal: &Terminal, flexible: bool) {
        let state = match self.state.upgrade() {
            Some(state) => state,
            None => return,
        };

        let workspace = state.workspace.borrow();
        let window_model = workspace
            .windows
            .iter()
            .find(|w| w.id == self.window_id)
            .cloned();
        if let Some(window_model) = window_model {
            let active_tab = window_model.active_tab();
            let tab_id = active_tab.id;
            let fallback = format!("{} — {}", window_model.title, active_tab.display_title());
            drop(workspace);
            let dynamic = format_terminal_title(terminal, &fallback, flexible);
            self.title_bar.update_dynamic(Some(&dynamic));

            state
                .workspace
                .borrow_mut()
                .update_tab_dynamic_title(self.window_id, tab_id, &dynamic);

            if let Some((title, flex, inner_active)) = {
                let ws = state.workspace.borrow();
                ws.windows
                    .iter()
                    .find(|w| w.id == self.window_id)
                    .and_then(|window| {
                        window.tabs.iter().find(|tab| tab.id == tab_id).map(|tab| {
                            let inner = match &tab.root {
                                LayoutNode::Tabs(group) => {
                                    group.tabs.get(group.active).map(|inner| {
                                        (inner.id, inner.display_title(), inner.is_title_flexible())
                                    })
                                }
                                _ => None,
                            };
                            (tab.display_title(), tab.is_title_flexible(), inner)
                        })
                    })
            } {
                if let Some(label) = self.tab_labels.borrow().get(&tab_id) {
                    label.set_text(&title, flex);
                    if flex {
                        label.update_dynamic(Some(&title));
                    }
                }

                if let Some((inner_id, inner_title, inner_flex)) = inner_active {
                    if let Some(label) = self.inner_tab_labels.borrow().get(&inner_id) {
                        label.set_text(&inner_title, inner_flex);
                        if inner_flex {
                            label.update_dynamic(Some(&inner_title));
                        }
                    }
                }
            }
        }
    }

    fn copy_active(&self) {
        if let Some(state) = self.state.upgrade() {
            if let Some(terminal) = self.active_terminal(&state) {
                terminal.copy_clipboard_format(Format::Text);
            }
        }
    }

    fn paste_active(&self) {
        if let Some(state) = self.state.upgrade() {
            if let Some(terminal) = self.active_terminal(&state) {
                terminal.paste_clipboard();
            }
        }
    }

    fn active_terminal(&self, state: &Rc<AppState>) -> Option<Terminal> {
        let ws = state.workspace.borrow();
        let window = ws.windows.iter().find(|w| w.id == self.window_id)?;
        let terminal_id = window.active_tab().active_terminal();
        state.registry.borrow().terminal(terminal_id)
    }

    fn close_window(&self) {
        self.window.close();
    }
}

struct TerminalRegistry {
    entries: HashMap<TerminalId, Rc<TerminalEntry>>,
    owner: Weak<AppState>,
}

impl TerminalRegistry {
    fn new(owner: Weak<AppState>) -> Self {
        Self {
            entries: HashMap::new(),
            owner,
        }
    }

    fn ensure_terminal(&mut self, id: TerminalId) {
        if self.entries.contains_key(&id) {
            return;
        }

        let terminal = Terminal::new();
        terminal.set_hexpand(true);
        terminal.set_vexpand(true);
        terminal.add_css_class("view");
        terminal.add_css_class("terminal");
        let entry = TerminalEntry::new(id, terminal.clone(), self.owner.clone());
        setup_terminal_theme(&terminal);
        spawn_shell(&terminal);
        self.entries.insert(id, entry);
    }

    fn attach_terminal(&mut self, id: TerminalId, window: WindowId, flexible: bool) -> Terminal {
        self.ensure_terminal(id);
        let entry = self.entries.get(&id).expect("terminal exists");
        if entry.terminal.parent().is_some() {
            entry.terminal.unparent();
        }
        entry.window_id.replace(Some(window));
        entry.flexible.set(flexible);
        entry.refresh_labels();
        entry.terminal.clone()
    }

    fn register_label(&mut self, id: TerminalId, label: &Label, flexible: bool) {
        if let Some(entry) = self.entries.get(&id) {
            entry.flexible.set(flexible);
            entry.register_label(label);
        }
    }

    fn terminal(&self, id: TerminalId) -> Option<Terminal> {
        self.entries.get(&id).map(|entry| entry.terminal.clone())
    }

    fn remove_terminal(&mut self, id: TerminalId) {
        self.entries.remove(&id);
    }

    fn window_for_terminal(&self, id: TerminalId) -> Option<WindowId> {
        self.entries
            .get(&id)
            .and_then(|entry| entry.window_id.get())
    }

    fn cleanup_for_window(&mut self, window: WindowId, keep: &[TerminalId]) {
        let keep: HashSet<_> = keep.iter().copied().collect();
        self.entries.retain(|id, entry| {
            if entry.window_id.get() == Some(window) && !keep.contains(id) {
                false
            } else {
                true
            }
        });
    }

    fn reapply_theme(&self) {
        for entry in self.entries.values() {
            apply_terminal_theme(&entry.terminal);
        }
    }
}

struct TerminalEntry {
    terminal: Terminal,
    window_id: Cell<Option<WindowId>>,
    flexible: Cell<bool>,
    labels: RefCell<Vec<glib::WeakRef<Label>>>,
}

impl TerminalEntry {
    fn new(id: TerminalId, terminal: Terminal, owner: Weak<AppState>) -> Rc<Self> {
        let entry = Rc::new(TerminalEntry {
            terminal: terminal.clone(),
            window_id: Cell::new(None),
            flexible: Cell::new(true),
            labels: RefCell::new(Vec::new()),
        });

        let weak_owner = owner.clone();
        terminal.connect_child_exited(move |_, _| {
            if let Some(owner) = weak_owner.upgrade() {
                owner.handle_terminal_exit(id);
            }
        });

        let weak_entry = Rc::downgrade(&entry);
        terminal.connect_window_title_notify(move |_| {
            if let Some(entry) = weak_entry.upgrade() {
                entry.refresh_labels();
            }
        });

        let weak_entry = Rc::downgrade(&entry);
        terminal.connect_current_directory_uri_notify(move |_| {
            if let Some(entry) = weak_entry.upgrade() {
                entry.refresh_labels();
            }
        });

        entry
    }

    fn register_label(&self, label: &Label) {
        self.labels
            .borrow_mut()
            .retain(|weak| weak.upgrade().is_some());
        self.labels.borrow_mut().push(label.downgrade());
        self.refresh_labels();
    }

    fn refresh_labels(&self) {
        let flexible = self.flexible.get();
        let text = format_terminal_title(&self.terminal, "Terminal", flexible);
        self.labels.borrow_mut().retain(|weak| {
            if let Some(label) = weak.upgrade() {
                label.set_text(&text);
                true
            } else {
                false
            }
        });
    }
}

#[allow(deprecated)]
fn setup_terminal_theme(terminal: &Terminal) {
    apply_terminal_theme(terminal);

    terminal.connect_realize(|term| {
        apply_terminal_theme(term);
    });
}

#[allow(deprecated)]
fn apply_terminal_theme(terminal: &Terminal) {
    if let Some((fg, bg)) = widget_theme_colors(terminal) {
        terminal.set_colors(Some(&fg), Some(&bg), &[]);
        terminal.set_color_cursor(Some(&fg));
        terminal.set_color_cursor_foreground(Some(&bg));
        let highlight = mix_colors(&fg, &bg, 0.25);
        terminal.set_color_highlight(Some(&highlight));
        terminal.set_color_highlight_foreground(Some(&fg));
    } else {
        terminal.set_default_colors();
    }
}

#[allow(deprecated)]
fn widget_theme_colors<W: IsA<gtk4::Widget>>(widget: &W) -> Option<(RGBA, RGBA)> {
    let widget_ref = widget.as_ref();
    let context = widget_ref.style_context();

    if let Some(colors) = colors_from_context(&context) {
        return Some(colors);
    }

    if let Some(parent) = widget_ref.parent() {
        return widget_theme_colors(&parent);
    }

    None
}

fn mix_colors(a: &RGBA, b: &RGBA, factor: f32) -> RGBA {
    let inv = 1.0 - factor;
    RGBA::new(
        a.red() * factor + b.red() * inv,
        a.green() * factor + b.green() * inv,
        a.blue() * factor + b.blue() * inv,
        a.alpha() * factor + b.alpha() * inv,
    )
}

#[allow(deprecated)]
fn colors_from_context(context: &StyleContext) -> Option<(RGBA, RGBA)> {
    let fg = context
        .lookup_color("theme_fg_color")
        .or_else(|| context.lookup_color("window_fg_color"))
        .or_else(|| context.lookup_color("view_fg_color"));
    let bg = context
        .lookup_color("theme_bg_color")
        .or_else(|| context.lookup_color("window_bg_color"))
        .or_else(|| context.lookup_color("view_bg_color"));

    match (fg, bg) {
        (Some(fg), Some(bg)) => Some((fg, bg)),
        _ => None,
    }
}

#[allow(deprecated)]
fn ensure_custom_css() {
    CUSTOM_CSS_PROVIDER.with(|cell| {
        if cell.borrow().is_some() {
            return;
        }

        if let Some(display) = gtk4::gdk::Display::default() {
            let provider = gtk4::CssProvider::new();
            let css = r#"
.custom-title {
    background-color: #c00000;
    color: #ffffff;
}

.custom-title * {
    color: #ffffff;
}

.custom-title entry {
    background-color: rgba(255, 255, 255, 0.12);
    color: #ffffff;
    caret-color: #ffffff;
    border-color: rgba(255, 255, 255, 0.35);
}

.custom-title entry selection {
    background-color: rgba(255, 255, 255, 0.35);
    color: #c00000;
}
"#;
            provider.load_from_data(css);
            gtk4::style_context_add_provider_for_display(
                &display,
                &provider,
                gtk4::STYLE_PROVIDER_PRIORITY_APPLICATION,
            );
            cell.borrow_mut().replace(provider);
        }
    });
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
    layout.append_item(&menu_item(NewInnerTab, "term.new_inner_tab", bindings));
    layout.append_item(&menu_item(SplitHorizontal, "term.split_h", bindings));
    layout.append_item(&menu_item(SplitVertical, "term.split_v", bindings));

    let secondary = gio::Menu::new();
    secondary.append_item(&menu_item(Settings, "term.settings", bindings));
    secondary.append_item(&menu_item(Close, "term.close", bindings));
    secondary.append_item(&menu_item(CloseInnerTab, "term.close_inner_tab", bindings));

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
        NewInnerTab => "term.new_inner_tab",
        SplitHorizontal => "term.split_h",
        SplitVertical => "term.split_v",
        Settings => "term.settings",
        Close => "term.close",
        CloseInnerTab => "term.close_inner_tab",
    }
}

fn action_label(action: ActionId) -> &'static str {
    ACTION_DEFS
        .iter()
        .find(|(id, _)| *id == action)
        .map(|(_, label)| *label)
        .unwrap_or("")
}

fn format_terminal_title(terminal: &Terminal, fallback: &str, flexible: bool) -> String {
    let mut display_title = terminal.window_title().and_then(|s| {
        let trimmed = s.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_string())
        }
    });
    if flexible {
        if let Some(dir_uri) = terminal.current_directory_uri() {
            if let Some(path) = gio::File::for_uri(&dir_uri).path() {
                let dir = path.display().to_string();
                if let Some(title) = display_title.as_mut() {
                    *title = format!("{} ({dir})", title.trim());
                } else {
                    display_title = Some(dir);
                }
            }
        }
    }
    display_title.unwrap_or_else(|| fallback.to_string())
}
