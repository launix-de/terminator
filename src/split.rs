//! Split helpers and utilities.
use crate::model::SplitOrientation;

#[allow(dead_code)]
pub fn orientation_from_pointer(x: f64, y: f64, w: f64, h: f64) -> SplitOrientation {
    let dx = ((x / w) - 0.5).abs();
    let dy = ((y / h) - 0.5).abs();
    if dx > dy {
        SplitOrientation::Horizontal
    } else {
        SplitOrientation::Vertical
    }
}

