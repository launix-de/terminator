//! Centralized LayoutNode tree operations.
//!
//! This module implements all behavior for the layout tree (`LayoutNode`),
//! covering terminals, splits, and tab groups in one place. Keeping these
//! operations here avoids duplication and makes the data model easier to reason about.

use uuid::Uuid;
use crate::model::{LayoutNode, TabGroup, InnerTab, TerminalLeaf, NodeId, TerminalId, InnerTabId, SplitNode, SplitOrientation};

impl LayoutNode {
    pub(crate) fn as_tab_group_mut(&mut self) -> Option<&mut TabGroup> {
        match self {
            LayoutNode::Tabs(group) => Some(group),
            _ => None,
        }
    }

    pub(crate) fn collect_terminal_ids(&self, out: &mut Vec<TerminalId>) {
        match self {
            LayoutNode::Terminal(leaf) => out.push(leaf.terminal_id),
            LayoutNode::Split(split) => {
                for child in &split.children {
                    child.collect_terminal_ids(out);
                }
            }
            LayoutNode::Tabs(group) => {
                for inner in &group.tabs {
                    inner.root.collect_terminal_ids(out);
                }
            }
        }
    }

    pub(crate) fn first_terminal_id(&self) -> Option<TerminalId> {
        match self {
            LayoutNode::Terminal(leaf) => Some(leaf.terminal_id),
            LayoutNode::Split(split) => split
                .children
                .iter()
                .find_map(|child| child.first_terminal_id()),
            LayoutNode::Tabs(group) => group
                .tabs
                .get(group.active)
                .and_then(|inner| inner.root.first_terminal_id()),
        }
    }

    pub(crate) fn last_terminal_id(&self) -> Option<TerminalId> {
        match self {
            LayoutNode::Terminal(leaf) => Some(leaf.terminal_id),
            LayoutNode::Split(split) => split
                .children
                .iter()
                .rev()
                .find_map(|child| child.last_terminal_id()),
            LayoutNode::Tabs(group) => group
                .tabs
                .get(group.active)
                .and_then(|inner| inner.root.last_terminal_id()),
        }
    }

    pub fn contains_terminal(&self, id: TerminalId) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => leaf.terminal_id == id,
            LayoutNode::Split(split) => split.children.iter().any(|c| c.contains_terminal(id)),
            LayoutNode::Tabs(group) => group.tabs.iter().any(|i| i.root.contains_terminal(id)),
        }
    }

    pub fn find_inner_id_for_terminal(&self, target: TerminalId) -> Option<InnerTabId> {
        match self {
            LayoutNode::Terminal(_) => None,
            LayoutNode::Split(split) => {
                for child in &split.children {
                    if let Some(id) = child.find_inner_id_for_terminal(target) {
                        return Some(id);
                    }
                }
                None
            }
            LayoutNode::Tabs(group) => {
                for inner in &group.tabs {
                    if inner.root.contains_terminal(target) {
                        return Some(inner.id);
                    }
                    if let Some(id) = inner.root.find_inner_id_for_terminal(target) {
                        return Some(id);
                    }
                }
                None
            }
        }
    }

    // If there is a Tabs group that contains the target terminal, append a new inner tab to that group.
    // Returns true if a group was found and modified.
    pub(crate) fn add_inner_tab_to_group_containing_terminal(
        &mut self,
        target: TerminalId,
        new_inner_id: InnerTabId,
        new_terminal_id: TerminalId,
    ) -> bool {
        match self {
            LayoutNode::Tabs(group) => {
                if group.tabs.iter().any(|i| i.root.contains_terminal(target)) {
                    let new_inner = InnerTab {
                        id: new_inner_id,
                        title: String::from("Terminal"),
                        root: LayoutNode::Terminal(TerminalLeaf {
                            node_id: NodeId(Uuid::new_v4()),
                            terminal_id: new_terminal_id,
                            title: String::from("Terminal"),
                            title_flexible: true,
                        }),
                        focus: new_terminal_id,
                        flexible: true,
                    };
                    group.tabs.push(new_inner);
                    group.active = group.tabs.len() - 1;
                    true
                } else {
                    for inner in &mut group.tabs {
                        if inner
                            .root
                            .add_inner_tab_to_group_containing_terminal(target, new_inner_id, new_terminal_id)
                        {
                            return true;
                        }
                    }
                    false
                }
            }
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.add_inner_tab_to_group_containing_terminal(target, new_inner_id, new_terminal_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Terminal(_) => false,
        }
    }

    // Wrap the subtree that contains `target` into a Tabs group holding the existing subtree
    // and a new inner tab with `new_terminal_id`.
    // Returns true if a subtree was found and wrapped.
    pub(crate) fn wrap_subtree_containing_terminal_with_tabs(
        &mut self,
        target: TerminalId,
        new_inner_id: InnerTabId,
        new_terminal_id: TerminalId,
    ) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => {
                if leaf.terminal_id == target {
                    let orig_term = leaf.terminal_id;
                    let existing = std::mem::replace(
                        self,
                        LayoutNode::Tabs(TabGroup {
                            node_id: NodeId(Uuid::new_v4()),
                            tabs: Vec::new(),
                            active: 0,
                        }),
                    );
                    if let LayoutNode::Tabs(group) = self {
                        let first_terminal = existing.first_terminal_id().unwrap_or(orig_term);
                        let first_inner = InnerTab {
                            id: InnerTabId(Uuid::new_v4()),
                            title: String::from("Terminal"),
                            root: existing,
                            focus: first_terminal,
                            flexible: true,
                        };
                        let second_inner = InnerTab {
                            id: new_inner_id,
                            title: String::from("Terminal"),
                            root: LayoutNode::Terminal(TerminalLeaf {
                                node_id: NodeId(Uuid::new_v4()),
                                terminal_id: new_terminal_id,
                                title: String::from("Terminal"),
                                title_flexible: true,
                            }),
                            focus: new_terminal_id,
                            flexible: true,
                        };
                        group.tabs.push(first_inner);
                        group.tabs.push(second_inner);
                        group.active = 1;
                        true
                    } else {
                        false
                    }
                } else {
                    false
                }
            }
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.wrap_subtree_containing_terminal_with_tabs(target, new_inner_id, new_terminal_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                for inner in &mut group.tabs {
                    if inner.root.contains_terminal(target) {
                        if inner
                            .root
                            .wrap_subtree_containing_terminal_with_tabs(target, new_inner_id, new_terminal_id)
                        {
                            return true;
                        }
                    }
                }
                false
            }
        }
    }

    pub(crate) fn remove_inner_tab_by_id_recursive(&mut self, inner_id: InnerTabId) -> bool {
        match self {
            LayoutNode::Terminal(_) => false,
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.remove_inner_tab_by_id_recursive(inner_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                if let Some(idx) = group.tabs.iter().position(|i| i.id == inner_id) {
                    group.tabs.remove(idx);
                    if group.tabs.is_empty() {
                        *self = LayoutNode::Split(SplitNode {
                            node_id: NodeId(Uuid::new_v4()),
                            orientation: SplitOrientation::Vertical,
                            children: Vec::new(),
                        });
                    } else {
                        if idx == 0 {
                            group.active = 0;
                        } else if idx - 1 < group.tabs.len() {
                            group.active = idx - 1;
                        } else {
                            group.active = group.tabs.len() - 1;
                        }
                    }
                    true
                } else {
                    for inner in &mut group.tabs {
                        if inner.root.remove_inner_tab_by_id_recursive(inner_id) {
                            return true;
                        }
                    }
                    false
                }
            }
        }
    }

    pub fn add_existing_terminal_to_group_with_inner_id(
        &mut self,
        target_inner: InnerTabId,
        moving_terminal_id: TerminalId,
    ) -> bool {
        match self {
            LayoutNode::Terminal(_) => false,
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.add_existing_terminal_to_group_with_inner_id(target_inner, moving_terminal_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                let contains_target = group.tabs.iter().any(|i| i.id == target_inner);
                if contains_target {
                    let new_inner = InnerTab {
                        id: InnerTabId(Uuid::new_v4()),
                        title: String::from("Terminal"),
                        root: LayoutNode::Terminal(TerminalLeaf {
                            node_id: NodeId(Uuid::new_v4()),
                            terminal_id: moving_terminal_id,
                            title: String::from("Terminal"),
                            title_flexible: true,
                        }),
                        focus: moving_terminal_id,
                        flexible: true,
                    };
                    group.tabs.push(new_inner);
                    group.active = group.tabs.len() - 1;
                    true
                } else {
                    for inner in &mut group.tabs {
                        if inner
                            .root
                            .add_existing_terminal_to_group_with_inner_id(target_inner, moving_terminal_id)
                        {
                            return true;
                        }
                    }
                    false
                }
            }
        }
    }

    pub(crate) fn find_adjacent_terminal(
        &self,
        target: TerminalId,
        orientation: SplitOrientation,
        forward: bool,
    ) -> Option<TerminalId> {
        match self {
            LayoutNode::Terminal(_) => None,
            LayoutNode::Split(split) => {
                for (index, child) in split.children.iter().enumerate() {
                    if child.contains_terminal(target) {
                        if let Some(inner) = child.find_adjacent_terminal(target, orientation, forward) {
                            return Some(inner);
                        }
                        if split.orientation == orientation {
                            if forward {
                                if let Some(next_child) = split.children.get(index + 1) {
                                    return next_child.first_terminal_id();
                                }
                            } else if index > 0 {
                                if let Some(prev_child) = split.children.get(index - 1) {
                                    return prev_child.last_terminal_id();
                                }
                            }
                        }
                        return None;
                    }
                }
                None
            }
            LayoutNode::Tabs(group) => {
                for inner in &group.tabs {
                    if inner.root.contains_terminal(target) {
                        return inner
                            .root
                            .find_adjacent_terminal(target, orientation, forward);
                    }
                }
                None
            }
        }
    }

    pub(crate) fn replace_leaf_with_split(
        &mut self,
        target: TerminalId,
        orientation: SplitOrientation,
        new_terminal_id: TerminalId,
    ) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => {
                if leaf.terminal_id == target {
                    let existing = std::mem::replace(
                        self,
                        LayoutNode::Split(SplitNode {
                            node_id: NodeId(Uuid::new_v4()),
                            orientation,
                            children: Vec::new(),
                        }),
                    );
                    if let LayoutNode::Split(split_node) = self {
                        let existing_leaf = existing;
                        let new_leaf = LayoutNode::Terminal(TerminalLeaf {
                            node_id: NodeId(Uuid::new_v4()),
                            terminal_id: new_terminal_id,
                            title: String::from("Terminal"),
                            title_flexible: true,
                        });
                        split_node.children.push(existing_leaf);
                        split_node.children.push(new_leaf);
                        true
                    } else {
                        false
                    }
                } else {
                    false
                }
            }
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.replace_leaf_with_split(target, orientation, new_terminal_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                for (idx, inner) in group.tabs.iter_mut().enumerate() {
                    if inner
                        .root
                        .replace_leaf_with_split(target, orientation, new_terminal_id)
                    {
                        group.active = idx;
                        return true;
                    }
                }
                false
            }
        }
    }

    pub(crate) fn replace_leaf_with_split_existing(
        &mut self,
        target: TerminalId,
        orientation: SplitOrientation,
        moving_terminal_id: TerminalId,
    ) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => {
                if leaf.terminal_id == target {
                    let existing = std::mem::replace(
                        self,
                        LayoutNode::Split(SplitNode {
                            node_id: NodeId(Uuid::new_v4()),
                            orientation,
                            children: Vec::new(),
                        }),
                    );
                    if let LayoutNode::Split(split_node) = self {
                        let existing_leaf = existing;
                        let new_leaf = LayoutNode::Terminal(TerminalLeaf {
                            node_id: NodeId(Uuid::new_v4()),
                            terminal_id: moving_terminal_id,
                            title: String::from("Terminal"),
                            title_flexible: true,
                        });
                        split_node.children.push(existing_leaf);
                        split_node.children.push(new_leaf);
                        true
                    } else {
                        false
                    }
                } else {
                    false
                }
            }
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.replace_leaf_with_split_existing(
                        target,
                        orientation,
                        moving_terminal_id,
                    ) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                for (idx, inner) in group.tabs.iter_mut().enumerate() {
                    if inner
                        .root
                        .replace_leaf_with_split_existing(target, orientation, moving_terminal_id)
                    {
                        group.active = idx;
                        return true;
                    }
                }
                false
            }
        }
    }

    pub(crate) fn remove_terminal(&mut self, target: TerminalId) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => {
                if leaf.terminal_id == target {
                    *self = LayoutNode::Split(SplitNode {
                        node_id: NodeId(Uuid::new_v4()),
                        orientation: SplitOrientation::Vertical,
                        children: Vec::new(),
                    });
                    true
                } else {
                    false
                }
            }
            LayoutNode::Split(split) => {
                let mut removed_any = false;
                for child in &mut split.children {
                    if child.remove_terminal(target) {
                        removed_any = true;
                    }
                }
                split.children
                    .retain(|child| !matches!(child, LayoutNode::Terminal(leaf) if leaf.terminal_id == target));
                split.children.retain(|child| !child.is_empty());
                match split.children.len() {
                    0 => {}
                    1 => {
                        let only = split.children.remove(0);
                        *self = only;
                    }
                    _ => {}
                }
                removed_any
            }
            LayoutNode::Tabs(group) => {
                if let Some(idx) = group
                    .tabs
                    .iter()
                    .enumerate()
                    .find_map(|(idx, inner)| if inner.root.contains_terminal(target) { Some(idx) } else { None })
                {
                    let inner = &mut group.tabs[idx];
                    let removed = inner.root.remove_terminal(target);
                    if inner.root.is_empty() {
                        group.tabs.remove(idx);
                        if group.tabs.is_empty() {
                            *self = LayoutNode::Split(SplitNode {
                                node_id: NodeId(Uuid::new_v4()),
                                orientation: SplitOrientation::Vertical,
                                children: Vec::new(),
                            });
                        } else {
                            if group.active >= group.tabs.len() {
                                group.active = group.tabs.len() - 1;
                            } else if group.active == idx && idx > 0 {
                                group.active = idx - 1;
                            }
                        }
                    }
                    removed
                } else {
                    false
                }
            }
        }
    }

    pub(crate) fn is_empty(&self) -> bool {
        match self {
            LayoutNode::Terminal(_) => false,
            LayoutNode::Split(split) => split.children.is_empty(),
            LayoutNode::Tabs(group) => group.tabs.is_empty(),
        }
    }
}
