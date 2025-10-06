//! Terminal registry and window-level helpers.
use std::{cell::{Cell, RefCell}, rc::{Rc, Weak}, collections::HashMap};
use gtk4::{prelude::*, Label};
use gtk4::gdk::RGBA;
use vte4::Terminal;
use vte4::prelude::*;
use crate::model::{WindowId, TerminalId};

pub struct TerminalRegistry {
    entries: HashMap<TerminalId, Rc<TerminalEntry>>,
    owner: Weak<crate::AppState>,
}

impl TerminalRegistry {
    pub fn new(owner: Weak<crate::AppState>) -> Self {
        Self { entries: HashMap::new(), owner }
    }

    pub fn ensure_terminal(&mut self, id: TerminalId) {
        if self.entries.contains_key(&id) { return; }
        let terminal = Terminal::new();
        terminal.set_hexpand(true);
        terminal.set_vexpand(true);
        terminal.add_css_class("view");
        terminal.add_css_class("terminal");
        let entry = TerminalEntry::new(id, terminal.clone(), self.owner.clone());
        setup_terminal_theme(&terminal);
        // Spawn once when the terminal is created. If the app requested a specific
        // command (via CLI), use it; otherwise spawn the default shell.
        if let Some(owner) = self.owner.upgrade() {
            if let Some(exec) = owner.pending_exec.borrow_mut().take() {
                crate::spawn_program(&terminal, exec);
            } else {
                crate::spawn_shell(&terminal);
            }
        } else {
            crate::spawn_shell(&terminal);
        }
        self.entries.insert(id, entry);
    }

    pub fn attach_terminal(&mut self, id: TerminalId, window: WindowId, flexible: bool) -> Terminal {
        self.ensure_terminal(id);
        let entry = self.entries.get(&id).expect("terminal exists");
        if entry.terminal.parent().is_some() { entry.terminal.unparent(); }
        entry.window_id.replace(Some(window));
        entry.flexible.set(flexible);
        entry.refresh_labels();
        entry.terminal.clone()
    }

    pub fn register_label(&mut self, id: TerminalId, label: &Label, flexible: bool) {
        if let Some(entry) = self.entries.get(&id) {
            entry.flexible.set(flexible);
            entry.register_label(label);
        }
    }

    pub fn terminal(&self, id: TerminalId) -> Option<Terminal> {
        self.entries.get(&id).map(|entry| entry.terminal.clone())
    }

    pub fn remove_terminal(&mut self, id: TerminalId) { self.entries.remove(&id); }

    pub fn window_for_terminal(&self, id: TerminalId) -> Option<WindowId> {
        self.entries.get(&id).and_then(|entry| entry.window_id.get())
    }

    pub fn cleanup_for_window(&mut self, window: WindowId, keep: &[TerminalId]) {
        let keep: std::collections::HashSet<_> = keep.iter().copied().collect();
        self.entries.retain(|id, entry| !(entry.window_id.get()==Some(window) && !keep.contains(id)));
    }

    pub fn reapply_theme(&self) { for entry in self.entries.values() { apply_terminal_theme(&entry.terminal); } }
}

pub struct TerminalEntry {
    id: TerminalId,
    terminal: Terminal,
    window_id: Cell<Option<WindowId>>,
    flexible: Cell<bool>,
    labels: RefCell<Vec<gtk4::glib::WeakRef<Label>>>,
    owner: Weak<crate::AppState>,
}

impl TerminalEntry {
    fn new(id: TerminalId, terminal: Terminal, owner: Weak<crate::AppState>) -> Rc<Self> {
        let entry = Rc::new(TerminalEntry { id, terminal: terminal.clone(), window_id: Cell::new(None), flexible: Cell::new(true), labels: RefCell::new(Vec::new()), owner: owner.clone() });
        let weak_owner = owner.clone();
        terminal.connect_child_exited(move |_, _| { if let Some(owner) = weak_owner.upgrade() { owner.handle_terminal_exit(id); } });
        let weak_entry = Rc::downgrade(&entry);
        terminal.connect_window_title_notify(move |_| { if let Some(entry) = weak_entry.upgrade() { entry.refresh_labels(); } });
        let weak_entry = Rc::downgrade(&entry);
        terminal.connect_current_directory_uri_notify(move |_| { if let Some(entry) = weak_entry.upgrade() { entry.refresh_labels(); } });
        entry
    }

    fn register_label(&self, label: &Label) {
        self.labels.borrow_mut().retain(|w| w.upgrade().is_some());
        self.labels.borrow_mut().push(label.downgrade());
        self.refresh_labels();
    }

    fn refresh_labels(&self) {
        let flexible = self.flexible.get();
        let text = crate::format_terminal_title(&self.terminal, "Terminal", flexible);
        self.labels.borrow_mut().retain(|weak| {
            if let Some(label) = weak.upgrade() { label.set_text(&text); true } else { false }
        });
        if let Some(owner) = self.owner.upgrade() { owner.handle_terminal_title_changed(self.id); }
    }
}

#[allow(deprecated)]
pub fn setup_terminal_theme(terminal: &Terminal) { apply_terminal_theme(terminal); terminal.connect_realize(|term| { apply_terminal_theme(term); }); }

#[allow(deprecated)]
pub fn apply_terminal_theme(terminal: &Terminal) {
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
pub fn widget_theme_colors<W: gtk4::prelude::IsA<gtk4::Widget>>(widget: &W) -> Option<(RGBA, RGBA)> {
    let widget_ref = widget.as_ref();
    let context = widget_ref.style_context();
    if let Some(colors) = colors_from_context(&context) { return Some(colors); }
    if let Some(parent) = widget_ref.parent() { return widget_theme_colors(&parent); }
    None
}

pub fn mix_colors(a: &RGBA, b: &RGBA, factor: f32) -> RGBA {
    let inv = 1.0 - factor;
    RGBA::new(a.red()*factor + b.red()*inv, a.green()*factor + b.green()*inv, a.blue()*factor + b.blue()*inv, a.alpha()*factor + b.alpha()*inv)
}

#[allow(deprecated)]
pub fn colors_from_context(context: &gtk4::StyleContext) -> Option<(RGBA, RGBA)> {
    let fg = context.lookup_color("theme_fg_color").or_else(|| context.lookup_color("window_fg_color")).or_else(|| context.lookup_color("view_fg_color"));
    let bg = context.lookup_color("theme_bg_color").or_else(|| context.lookup_color("window_bg_color")).or_else(|| context.lookup_color("view_bg_color"));
    match (fg, bg) { (Some(fg), Some(bg)) => Some((fg, bg)), _ => None }
}
