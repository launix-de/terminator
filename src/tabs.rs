//! Tab label helpers used by both top-level and inner tabs.
use gtk4::{prelude::*, Box, Button, Image, Orientation};
use crate::ui::EditableTabLabel;

/// Build a tab label UI (label + close button) for use in both top-level and inner tab notebooks.
/// Returns (label_box, editable_label, close_button).
pub fn build_tab_label(title: String, flexible: bool) -> (Box, EditableTabLabel, Button) {
    let editable = EditableTabLabel::new(title, flexible);
    let label_widget = editable.widget();
    let label_box = Box::new(Orientation::Horizontal, 6);
    label_box.append(&label_widget);

    let close_btn = Button::new();
    close_btn.add_css_class("flat");
    let img = Image::from_icon_name("window-close-symbolic");
    close_btn.set_child(Some(&img));
    label_box.append(&close_btn);

    (label_box, editable, close_btn)
}

/// Apply close-button interaction defaults so it doesn't steal focus or trigger tab switches.
pub fn attach_close_capture(close_btn: &Button) {
    close_btn.set_focus_on_click(false);
    close_btn.set_can_focus(false);
    let close_capture = gtk4::GestureClick::new();
    close_capture.set_button(gtk4::gdk::ffi::GDK_BUTTON_PRIMARY as u32);
    close_capture.set_propagation_phase(gtk4::PropagationPhase::Capture);
    close_capture.connect_pressed(|g, _, _, _| {
        g.set_state(gtk4::EventSequenceState::Claimed);
    });
    close_btn.add_controller(close_capture);
}

// (Further TabContainer adapters to be added)
