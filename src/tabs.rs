use gtk4::{prelude::*, Box, Button, Image, Orientation};
use crate::ui::EditableTabLabel;

#[allow(dead_code)]
pub trait TabContainerOps {
    fn n_tabs(&self) -> usize;
    fn active_index(&self) -> usize;
}

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

