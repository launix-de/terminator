use gtk4::{
    Align, Box, Entry, EventControllerFocus, EventSequenceState, GestureClick, Orientation, Stack,
    StackTransitionType, gdk, prelude::*,
};
use gtk4::pango;
use std::{boxed::Box as StdBox, cell::Cell, cell::RefCell, rc::Rc};

#[derive(Clone)]
pub struct EditableTitleBar {
    inner: Rc<EditableTitleBarInner>,
}

impl EditableTitleBar {
    pub fn new(initial_title: impl Into<String>, fallback: impl Into<String>) -> Self {
        let initial_title = initial_title.into();
        let fallback_title = fallback.into();

        let container = Box::new(Orientation::Horizontal, 6);
        container.add_css_class("flat");
        container.add_css_class("titlebar");
        container.add_css_class("custom-title");
        container.set_margin_top(2);
        container.set_margin_bottom(2);
        container.set_margin_start(6);
        container.set_margin_end(6);
        container.set_hexpand(true);

        let label = gtk4::Label::new(Some(&initial_title));
        label.set_halign(Align::Start);
        label.set_xalign(0.0);
        label.set_hexpand(true);
        label.add_css_class("custom-title-label");
        label.set_single_line_mode(true);
        label.set_ellipsize(pango::EllipsizeMode::End);

        let entry = Entry::new();
        entry.set_hexpand(true);
        entry.add_css_class("custom-title-entry");

        let stack = Stack::new();
        stack.set_transition_type(StackTransitionType::Crossfade);
        stack.add_named(&label, Some("label"));
        stack.add_named(&entry, Some("entry"));
        stack.set_visible_child_name("label");

        container.append(&stack);

        let inner = Rc::new(EditableTitleBarInner {
            container,
            stack,
            label,
            entry,
            is_custom: Cell::new(false),
            flexible: Cell::new(true),
            last_dynamic: RefCell::new(initial_title.clone()),
            edit_callback: RefCell::new(None),
            fallback: RefCell::new(fallback_title),
            editing_original: RefCell::new(String::new()),
            editing_was_custom: Cell::new(false),
        });

        inner.setup_interactions();

        EditableTitleBar { inner }
    }

    pub fn widget(&self) -> Box {
        self.inner.container.clone()
    }

    pub fn update_dynamic(&self, title: Option<&str>) {
        if !self.inner.flexible.get() || self.inner.is_custom.get() {
            return;
        }
        if let Some(title) = title {
            self.inner.label.set_text(title);
            *self.inner.last_dynamic.borrow_mut() = title.to_string();
        } else {
            self.inner.label.set_text(&self.inner.fallback.borrow());
        }
    }

    pub fn set_flexible(&self, flexible: bool) {
        self.inner.flexible.set(flexible);
        if flexible {
            let dynamic = self.inner.last_dynamic.borrow().clone();
            self.inner.label.set_text(&dynamic);
        }
    }

    pub fn connect_committed<F: Fn(bool, String) + 'static>(&self, callback: F) {
        *self.inner.edit_callback.borrow_mut() = Some(StdBox::new(callback));
    }

    pub fn set_titles(&self, dynamic: &str, fallback: &str, flexible: bool) {
        self.inner.flexible.set(flexible);
        self.inner.is_custom.set(!flexible);
        self.inner.label.set_text(dynamic);
        *self.inner.fallback.borrow_mut() = fallback.to_string();
        *self.inner.last_dynamic.borrow_mut() = dynamic.to_string();
        self.inner.stack.set_visible_child_name("label");
    }

    #[allow(dead_code)]
    pub fn begin_edit(&self) {
        self.inner.begin_edit();
    }

    #[allow(dead_code)]
    pub fn commit_edit(&self, text: &str) {
        self.inner.finish_edit(Some(text.to_string()));
    }
}

struct EditableTitleBarInner {
    container: Box,
    stack: Stack,
    label: gtk4::Label,
    entry: Entry,
    is_custom: Cell<bool>,
    flexible: Cell<bool>,
    last_dynamic: RefCell<String>,
    edit_callback: RefCell<Option<StdBox<dyn Fn(bool, String)>>>,
    fallback: RefCell<String>,
    editing_original: RefCell<String>,
    editing_was_custom: Cell<bool>,
}

impl EditableTitleBarInner {
    fn setup_interactions(self: &Rc<Self>) {
        let gesture = GestureClick::new();
        gesture.set_button(gdk::ffi::GDK_BUTTON_PRIMARY as u32);
        gesture.set_propagation_phase(gtk4::PropagationPhase::Bubble);
        let this = Rc::clone(self);
        gesture.connect_released(move |gesture, n_press, _, _| {
            if n_press == 2 {
                gesture.set_state(EventSequenceState::Claimed);
                this.begin_edit();
            }
        });
        self.container.add_controller(gesture);

        let this = Rc::clone(self);
        self.entry.connect_activate(move |entry| {
            let text = entry.text().to_string();
            this.finish_edit(Some(text));
        });

        let focus_controller = EventControllerFocus::new();
        let this = Rc::clone(self);
        focus_controller.connect_leave(move |controller| {
            if let Some(widget) = controller.widget() {
                if let Ok(entry) = widget.downcast::<Entry>() {
                    let text = entry.text().to_string();
                    this.finish_edit(Some(text));
                }
            }
        });
        self.entry.add_controller(focus_controller);
    }

    fn begin_edit(&self) {
        let current = if self.is_custom.get() {
            self.label.text().to_string()
        } else {
            self.last_dynamic.borrow().clone()
        };
        self.editing_original.replace(current.clone());
        self.editing_was_custom.set(self.is_custom.get());
        self.entry.set_text(&current);
        self.stack.set_visible_child_name("entry");
        self.entry.select_region(0, -1);
        self.entry.grab_focus();
    }

    fn finish_edit(&self, value: Option<String>) {
        let text = value.unwrap_or_default().trim().to_string();
        let was_custom = self.editing_was_custom.get();
        let original = self.editing_original.borrow().clone();
        if text.is_empty() || (!was_custom && text == original) {
            self.is_custom.set(false);
            self.flexible.set(true);
            self.label.set_text(&self.last_dynamic.borrow());
        } else {
            self.is_custom.set(true);
            self.flexible.set(false);
            self.label.set_text(&text);
            *self.fallback.borrow_mut() = text.clone();
        }
        if let Some(callback) = &*self.edit_callback.borrow() {
            callback(self.is_custom.get(), self.label.text().to_string());
        }
        self.stack.set_visible_child_name("label");
    }
}

#[derive(Clone)]
pub struct EditableTabLabel {
    inner: Rc<EditableTabLabelInner>,
}

impl EditableTabLabel {
    pub fn new(initial_title: impl Into<String>, flexible: bool) -> Self {
        let initial_title = initial_title.into();

        let container = Box::new(Orientation::Horizontal, 4);
        let label = gtk4::Label::new(Some(&initial_title));
        label.set_xalign(0.0);
        label.set_hexpand(true);
        label.set_single_line_mode(true);
        label.set_ellipsize(pango::EllipsizeMode::End);

        let entry = Entry::new();
        entry.set_hexpand(true);

        let stack = Stack::new();
        stack.set_transition_type(StackTransitionType::Crossfade);
        stack.add_named(&label, Some("label"));
        stack.add_named(&entry, Some("entry"));
        stack.set_visible_child_name("label");

        container.append(&stack);

        let inner = Rc::new(EditableTabLabelInner {
            container,
            stack,
            label,
            entry,
            is_custom: Cell::new(!flexible),
            flexible: Cell::new(flexible),
            last_dynamic: RefCell::new(initial_title.clone()),
            fallback: RefCell::new(initial_title),
            edit_callback: RefCell::new(None),
            editing_original: RefCell::new(String::new()),
            editing_was_custom: Cell::new(false),
        });

        inner.setup_interactions();

        EditableTabLabel { inner }
    }

    pub fn widget(&self) -> Box {
        self.inner.container.clone()
    }

    pub fn update_dynamic(&self, title: Option<&str>) {
        if !self.inner.flexible.get() || self.inner.is_custom.get() {
            return;
        }
        if let Some(title) = title {
            self.inner.label.set_text(title);
            *self.inner.last_dynamic.borrow_mut() = title.to_string();
        } else {
            self.inner.label.set_text(&self.inner.fallback.borrow());
        }
    }

    pub fn set_text(&self, title: &str, flexible: bool) {
        self.inner.flexible.set(flexible);
        self.inner.is_custom.set(!flexible);
        if !flexible {
            self.inner.label.set_text(title);
            *self.inner.fallback.borrow_mut() = title.to_string();
        } else {
            self.inner.label.set_text(title);
            *self.inner.last_dynamic.borrow_mut() = title.to_string();
        }
    }

    #[allow(dead_code)]
    pub fn set_flexible(&self, flexible: bool) {
        self.inner.flexible.set(flexible);
        if flexible && !self.inner.is_custom.get() {
            let dynamic = self.inner.last_dynamic.borrow().clone();
            self.inner.label.set_text(&dynamic);
        }
    }

    pub fn connect_committed<F: Fn(bool, String) + 'static>(&self, callback: F) {
        *self.inner.edit_callback.borrow_mut() = Some(StdBox::new(callback));
    }

    pub fn set_max_width_chars(&self, chars: i32) {
        self.inner.label.set_max_width_chars(chars);
        self.inner.label.set_width_chars(chars);
    }

    pub fn set_ellipsize_end(&self) {
        self.inner.label.set_single_line_mode(true);
        self.inner.label.set_ellipsize(pango::EllipsizeMode::End);
    }
}

struct EditableTabLabelInner {
    container: Box,
    stack: Stack,
    label: gtk4::Label,
    entry: Entry,
    is_custom: Cell<bool>,
    flexible: Cell<bool>,
    last_dynamic: RefCell<String>,
    fallback: RefCell<String>,
    edit_callback: RefCell<Option<StdBox<dyn Fn(bool, String)>>>,
    editing_original: RefCell<String>,
    editing_was_custom: Cell<bool>,
}

impl EditableTabLabelInner {
    fn setup_interactions(self: &Rc<Self>) {
        let gesture = GestureClick::new();
        gesture.set_button(gdk::ffi::GDK_BUTTON_PRIMARY as u32);
        gesture.set_propagation_phase(gtk4::PropagationPhase::Bubble);
        let this = Rc::clone(self);
        gesture.connect_released(move |gesture, n_press, _, _| {
            if n_press == 2 {
                gesture.set_state(EventSequenceState::Claimed);
                this.begin_edit();
            }
        });
        self.container.add_controller(gesture);

        let this = Rc::clone(self);
        self.entry.connect_activate(move |entry| {
            let text = entry.text().to_string();
            this.finish_edit(Some(text));
        });

        let focus_controller = EventControllerFocus::new();
        let this = Rc::clone(self);
        focus_controller.connect_leave(move |controller| {
            if let Some(widget) = controller.widget() {
                if let Ok(entry) = widget.downcast::<Entry>() {
                    let text = entry.text().to_string();
                    this.finish_edit(Some(text));
                }
            }
        });
        self.entry.add_controller(focus_controller);
    }

    fn begin_edit(&self) {
        let current = if self.is_custom.get() {
            self.label.text().to_string()
        } else {
            self.last_dynamic.borrow().clone()
        };
        self.editing_original.replace(current.clone());
        self.editing_was_custom.set(self.is_custom.get());
        self.entry.set_text(&current);
        self.stack.set_visible_child_name("entry");
        self.entry.select_region(0, -1);
        self.entry.grab_focus();
    }

    fn finish_edit(&self, value: Option<String>) {
        let text = value.unwrap_or_default().trim().to_string();
        let was_custom = self.editing_was_custom.get();
        let original = self.editing_original.borrow().clone();
        if text.is_empty() || (!was_custom && text == original) {
            self.is_custom.set(false);
            self.flexible.set(true);
            self.label.set_text(&self.last_dynamic.borrow());
        } else {
            self.is_custom.set(true);
            self.flexible.set(false);
            self.label.set_text(&text);
            *self.fallback.borrow_mut() = text.clone();
        }
        if let Some(callback) = &*self.edit_callback.borrow() {
            callback(self.is_custom.get(), self.label.text().to_string());
        }
        self.stack.set_visible_child_name("label");
    }
}
