use std::collections::HashMap;
use uuid::Uuid;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct WindowId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct TabId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct InnerTabId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct NodeId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct TerminalId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum SplitOrientation {
    Horizontal,
    Vertical,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ActionId {
    Copy,
    Paste,
    NewWindow,
    NewTab,
    NewInnerTab,
    SplitHorizontal,
    SplitVertical,
    Close,
    CloseInnerTab,
    Settings,
    FocusLeft,
    FocusRight,
    FocusUp,
    FocusDown,
    NextTab,
    PrevTab,
}

pub type KeybindingMap = HashMap<ActionId, Vec<String>>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FocusDirection {
    Left,
    Right,
    Up,
    Down,
}

#[derive(Clone, Debug)]
pub struct WorkspaceModel {
    pub windows: Vec<WindowModel>,
    pub keybindings: KeybindingMap,
}

#[derive(Clone, Debug)]
pub struct WindowModel {
    pub id: WindowId,
    pub title: String,
    pub tabs: Vec<TabModel>,
    pub active_tab: usize,
}

#[derive(Clone, Debug)]
pub struct TabModel {
    pub id: TabId,
    pub root: LayoutNode,
    pub focus: TerminalId,
    pub title: String,
    pub title_flexible: bool,
    pub dynamic_title: String,
}

#[derive(Clone, Debug)]
pub enum LayoutNode {
    Terminal(TerminalLeaf),
    Split(SplitNode),
    Tabs(TabGroup),
}

#[derive(Clone, Debug)]
pub struct TerminalLeaf {
    #[allow(dead_code)]
    pub node_id: NodeId,
    pub terminal_id: TerminalId,
    #[allow(dead_code)]
    pub title: String,
    pub title_flexible: bool,
}

#[derive(Clone, Debug)]
pub struct SplitNode {
    #[allow(dead_code)]
    pub node_id: NodeId,
    pub orientation: SplitOrientation,
    pub children: Vec<LayoutNode>,
}

#[derive(Clone, Debug)]
pub struct TabGroup {
    #[allow(dead_code)]
    pub node_id: NodeId,
    pub tabs: Vec<InnerTab>,
    pub active: usize,
}

#[derive(Clone, Debug)]
pub struct InnerTab {
    pub id: InnerTabId,
    pub title: String,
    pub root: LayoutNode,
    pub focus: TerminalId,
    pub flexible: bool,
}

impl WorkspaceModel {
    pub fn new_single_terminal() -> Self {
        let window_id = WindowId(Uuid::new_v4());
        let (tab, _term_id) = TabModel::single_terminal_tab();
        let keybindings = default_keybindings();
        WorkspaceModel {
            windows: vec![WindowModel {
                id: window_id,
                title: String::from("Terminator"),
                tabs: vec![tab],
                active_tab: 0,
            }],
            keybindings,
        }
    }

    pub fn add_window(&mut self) -> WindowId {
        let id = WindowId(Uuid::new_v4());
        let (tab, _term) = TabModel::single_terminal_tab();
        self.windows.push(WindowModel {
            id,
            title: String::from("Terminator"),
            tabs: vec![tab],
            active_tab: 0,
        });
        id
    }

    pub fn remove_window(&mut self, window_id: WindowId) {
        self.windows.retain(|w| w.id != window_id);
    }

    pub fn rename_window(&mut self, window_id: WindowId, title: String) {
        if let Some(w) = self.windows.iter_mut().find(|w| w.id == window_id) {
            w.title = title;
        }
    }

    // Move a terminal to split with a target terminal, creating a split at the target.
    // Returns true if the terminal was removed from its original location and inserted at target.
    #[allow(dead_code)]
    pub fn move_terminal_to_split(
        &mut self,
        window_id: WindowId,
        moving: TerminalId,
        target: TerminalId,
        orientation: SplitOrientation,
    ) -> bool {
        let window = match self.windows.iter_mut().find(|w| w.id == window_id) {
            Some(w) => w,
            None => return false,
        };

        // Find the index of the tab containing the target first to avoid overlapping borrows.
        let tab_index = match window
            .tabs
            .iter()
            .position(|t| t.contains_terminal(target))
        {
            Some(i) => i,
            None => return false,
        };

        // Remove moving terminal from wherever it is within this window
        let removed = window
            .tabs
            .iter_mut()
            .any(|t| t.remove_terminal(moving));
        if !removed {
            return false;
        }

        // Now operate on the previously found tab by index
        let tab = &mut window.tabs[tab_index];
        let replaced = tab
            .root
            .replace_leaf_with_split_existing(target, orientation, moving);
        if replaced {
            tab.set_focus_terminal(moving);
        }
        replaced
    }

    #[allow(dead_code)]
    /// Move an existing `terminal_id` into a brand new top-level tab in `window_id`.
    /// Returns the new tab id on success.
    pub fn move_terminal_to_new_tab(&mut self, window_id: WindowId, terminal_id: TerminalId) -> Option<TabId> {
        let window = self.windows.iter_mut().find(|w| w.id == window_id)?;
        // Remove from any tab
        let removed = window
            .tabs
            .iter_mut()
            .any(|t| t.remove_terminal(terminal_id));
        if !removed {
            return None;
        }
        // Create new tab with that terminal as single root
        let leaf = TerminalLeaf {
            node_id: NodeId(Uuid::new_v4()),
            terminal_id,
            title: String::from("Terminal"),
            title_flexible: true,
        };
        let tab = TabModel {
            id: TabId(Uuid::new_v4()),
            root: LayoutNode::Terminal(leaf),
            focus: terminal_id,
            title: String::from("Terminal"),
            title_flexible: true,
            dynamic_title: String::new(),
        };
        let id = tab.id;
        window.tabs.push(tab);
        window.active_tab = window.tabs.len() - 1;
        Some(id)
    }

    #[allow(dead_code)]
    pub fn move_terminal_to_new_window(&mut self, terminal_id: TerminalId) -> Option<WindowId> {
        // Remove from any existing window/tab
        let mut removed = false;
        for w in &mut self.windows {
            if w.tabs.iter_mut().any(|t| t.remove_terminal(terminal_id)) {
                removed = true;
                break;
            }
        }
        if !removed {
            return None;
        }
        // Create new window with this terminal
        let id = WindowId(Uuid::new_v4());
        let leaf = TerminalLeaf {
            node_id: NodeId(Uuid::new_v4()),
            terminal_id,
            title: String::from("Terminal"),
            title_flexible: true,
        };
        let tab = TabModel {
            id: TabId(Uuid::new_v4()),
            root: LayoutNode::Terminal(leaf),
            focus: terminal_id,
            title: String::from("Terminal"),
            title_flexible: true,
            dynamic_title: String::new(),
        };
        self.windows.push(WindowModel {
            id,
            title: String::from("Terminator"),
            tabs: vec![tab],
            active_tab: 0,
        });
        Some(id)
    }

    pub fn close_tab(&mut self, window_id: WindowId, tab_id: TabId) -> bool {
        if let Some(widx) = self.windows.iter().position(|w| w.id == window_id) {
            let window = &mut self.windows[widx];
            if let Some(tidx) = window.tabs.iter().position(|t| t.id == tab_id) {
                window.tabs.remove(tidx);
                if window.tabs.is_empty() {
                    self.windows.remove(widx);
                } else {
                    if window.active_tab >= window.tabs.len() {
                        window.active_tab = window.tabs.len() - 1;
                    }
                }
                return true;
            }
        }
        false
    }

    /// Find the first terminal id in the given tab (DFS order).
    pub fn first_terminal_in_tab(&self, window_id: WindowId, tab_id: TabId) -> Option<TerminalId> {
        let window = self.windows.iter().find(|w| w.id == window_id)?;
        let tab = window.tabs.iter().find(|t| t.id == tab_id)?;
        tab.first_terminal_id()
    }

    pub fn add_tab_to_window(&mut self, window_id: WindowId) -> Option<TabId> {
        let window = self.windows.iter_mut().find(|w| w.id == window_id)?;
        let (tab, first) = TabModel::single_terminal_tab();
        let id = tab.id;
        // Remember focus
        window.tabs.push(tab);
        window.active_tab = window.tabs.len() - 1;
        // Keep the compiler happy about usage of `first` if we need it later
        let _ = first;
        Some(id)
    }

    /// Set the active top-level tab for a window (no-op if not found).
    pub fn set_active_tab(&mut self, window_id: WindowId, tab_id: TabId) {
        if let Some(window) = self.windows.iter_mut().find(|w| w.id == window_id) {
            if let Some(idx) = window.tabs.iter().position(|t| t.id == tab_id) {
                window.active_tab = idx;
            }
        }
    }

    /// Focus the given terminal inside `tab_id`.
    /// Returns true when focus actually changed.
    pub fn set_active_terminal(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        terminal_id: TerminalId,
    ) -> bool {
        if let Some(window) = self.windows.iter_mut().find(|w| w.id == window_id) {
            if let Some(tab) = window.tabs.iter_mut().find(|t| t.id == tab_id) {
                return tab.set_focus_terminal(terminal_id);
            }
        }
        false
    }

    /// Find a neighbor for focus navigation relative to `terminal_id`.
    pub fn focus_neighbor(
        &self,
        window_id: WindowId,
        tab_id: TabId,
        terminal_id: TerminalId,
        direction: FocusDirection,
    ) -> Option<TerminalId> {
        let window = self.windows.iter().find(|w| w.id == window_id)?;
        let tab = window.tabs.iter().find(|t| t.id == tab_id)?;
        let (orientation, forward) = match direction {
            FocusDirection::Left => (SplitOrientation::Horizontal, false),
            FocusDirection::Right => (SplitOrientation::Horizontal, true),
            FocusDirection::Up => (SplitOrientation::Vertical, false),
            FocusDirection::Down => (SplitOrientation::Vertical, true),
        };
        tab.root
            .find_adjacent_terminal(terminal_id, orientation, forward)
    }

    /// Split the given terminal leaf by `orientation`.
    /// Returns the newly created terminal id on success and focuses it.
    pub fn split_terminal(
        &mut self,
        window_id: WindowId,
        terminal_id: TerminalId,
        orientation: SplitOrientation,
    ) -> Option<TerminalId> {
        let window = self.windows.iter_mut().find(|w| w.id == window_id)?;
        let tab = window
            .tabs
            .iter_mut()
            .find(|t| t.contains_terminal(terminal_id))?;
        let new_terminal_id = TerminalId(Uuid::new_v4());
        let replaced = tab.replace_leaf_with_split(terminal_id, orientation, new_terminal_id);
        if replaced {
            tab.set_focus_terminal(new_terminal_id);
            Some(new_terminal_id)
        } else {
            None
        }
    }

    /// Close a terminal. Removes empty nodes and collapses single-child splits.
    /// Returns Some(()) if a terminal was removed.
    pub fn close_terminal(&mut self, window_id: WindowId, terminal_id: TerminalId) -> Option<()> {
        let window_idx = self.windows.iter().position(|w| w.id == window_id)?;
        let window = &mut self.windows[window_idx];
        let tab_idx = window
            .tabs
            .iter()
            .position(|t| t.contains_terminal(terminal_id))?;
        let tab = &mut window.tabs[tab_idx];
        if !tab.remove_terminal(terminal_id) {
            return None;
        }
        if tab.is_empty() {
            window.tabs.remove(tab_idx);
            if window.tabs.is_empty() {
                // Remove the empty window entirely
                self.windows.remove(window_idx);
                return Some(());
            }
            // Adjust active index
            if window.active_tab >= window.tabs.len() {
                window.active_tab = window.tabs.len() - 1;
            }
        } else {
            // If we removed the active focus, choose a remaining one
            if !tab.contains_terminal(tab.active_terminal()) {
                if let Some(first) = tab.first_terminal_id() {
                    tab.set_focus_terminal(first);
                }
            }
        }
        Some(())
    }

    /// Rename a top-level tab and set its flexibility flag. Returns true on change.
    pub fn rename_tab(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        title: String,
        flexible: bool,
    ) -> bool {
        if let Some(window) = self.windows.iter_mut().find(|w| w.id == window_id) {
            if let Some(tab) = window.tabs.iter_mut().find(|t| t.id == tab_id) {
                tab.title = title;
                tab.title_flexible = flexible;
                return true;
            }
        }
        false
    }

    /// Rename an inner tab (inside a Tabs group) and set its flexibility flag.
    /// Returns true on change.
    pub fn rename_inner_tab(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        inner_id: InnerTabId,
        title: String,
        flexible: bool,
    ) -> bool {
        if let Some(window) = self.windows.iter_mut().find(|w| w.id == window_id) {
            if let Some(tab) = window.tabs.iter_mut().find(|t| t.id == tab_id) {
                if let Some(group) = tab.root.as_tabs_mut() {
                    if let Some(inner) = group.tabs.iter_mut().find(|i| i.id == inner_id) {
                        inner.title = title;
                        inner.flexible = flexible;
                        return true;
                    }
                }
            }
        }
        false
    }

    /// Add a new inner tab near the subtree that contains `from_terminal`.
    /// Prefers wrapping the exact subtree; otherwise adds to the nearest Tabs group; finally wraps the top-level.
    /// Returns the (inner_tab_id, new_terminal_id) on success and focuses the new terminal.
    pub fn add_inner_tab(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        from_terminal: TerminalId,
    ) -> Option<(InnerTabId, TerminalId)> {
        let window = self.windows.iter_mut().find(|w| w.id == window_id)?;
        let tab = window.tabs.iter_mut().find(|t| t.id == tab_id)?;

        let new_terminal_id = TerminalId(Uuid::new_v4());
        let inner_id = InnerTabId(Uuid::new_v4());

        // 1) Prefer wrapping the exact subtree that contains the target into a Tabs group
        if tab
            .root
            .wrap_subtree_with_tabs_at(from_terminal, inner_id, new_terminal_id)
        {
            tab.focus = new_terminal_id;
            return Some((inner_id, new_terminal_id));
        }

        // 2) Otherwise, if there's an existing Tabs group that contains the target somewhere,
        // append a new inner to that group (less precise, but acceptable fallback).
        if tab
            .root
            .add_inner_to_group_containing(from_terminal, inner_id, new_terminal_id)
        {
            tab.focus = new_terminal_id;
            return Some((inner_id, new_terminal_id));
        }

        // 3) Fallback: wrap the whole tab at top-level
        tab.ensure_tabs_group();
        if let LayoutNode::Tabs(group) = &mut tab.root {
            let new_inner = InnerTab {
                id: inner_id,
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
        }
        tab.focus = new_terminal_id;
        Some((inner_id, new_terminal_id))
    }

    // Move an existing terminal into a new inner tab within the Tabs group that contains
    // the given inner id.
    pub fn move_terminal_to_new_inner_tab(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        target_inner: InnerTabId,
        moving: TerminalId,
    ) -> bool {
        let window = match self.windows.iter_mut().find(|w| w.id == window_id) {
            Some(w) => w,
            None => return false,
        };
        // Find the tab index first to avoid overlapping borrows
        let tab_index = match window.tabs.iter().position(|t| t.id == tab_id) {
            Some(i) => i,
            None => return false,
        };
        // Remove moving from any tab in this window
        let removed = window.tabs.iter_mut().any(|t| t.remove_terminal(moving));
        if !removed {
            return false;
        }
        let tab = &mut window.tabs[tab_index];
        if tab
            .root
            .add_existing_terminal_to_group_by_inner_id(target_inner, moving)
        {
            tab.focus = moving;
            true
        } else {
            false
        }
    }

    pub fn close_inner_tab(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        inner_id: InnerTabId,
    ) -> bool {
        let window_idx = match self.windows.iter().position(|w| w.id == window_id) {
            Some(i) => i,
            None => return false,
        };
        let mut remove_parent_tab = false;
        let mut changed = false;
        {
            let window = &mut self.windows[window_idx];
            if let Some(tab_idx) = window.tabs.iter().position(|t| t.id == tab_id) {
                let tab = &mut window.tabs[tab_idx];
                // First, try removing from a top-level Tabs group
                if let Some(group) = tab.root.as_tabs_mut() {
                    if let Some(idx) = group.tabs.iter().position(|i| i.id == inner_id) {
                        group.tabs.remove(idx);
                        changed = true;
                        if group.tabs.is_empty() {
                            remove_parent_tab = true;
                        } else {
                            // Keep the Tabs group even when only one inner remains; just update active and focus
                            if idx == 0 {
                                group.active = 0;
                            } else if idx - 1 < group.tabs.len() {
                                group.active = idx - 1;
                            } else {
                                group.active = group.tabs.len() - 1;
                            }
                            if let Some(first) = group.tabs[group.active].root.first_terminal_id() {
                                tab.focus = first;
                            }
                        }
                    }
                }
                // If not changed, try nested removal anywhere in the tree
                if !changed {
                    if tab.root.remove_inner_by_id_recursive(inner_id) {
                        changed = true;
                        // Fix focus if it points to a removed terminal
                        if !tab.contains_terminal(tab.focus) {
                            if let Some(first) = tab.first_terminal_id() {
                                tab.focus = first;
                            }
                        }
                    }
                }
            }
        }
        if changed && remove_parent_tab {
            // Remove the entire parent tab; adjust active index and remove window if needed
            let window = &mut self.windows[window_idx];
            if let Some(tab_idx) = window.tabs.iter().position(|t| t.id == tab_id) {
                window.tabs.remove(tab_idx);
                if window.tabs.is_empty() {
                    // remove whole window
                    self.windows.remove(window_idx);
                } else {
                    if window.active_tab >= window.tabs.len() {
                        window.active_tab = window.tabs.len() - 1;
                    }
                }
            }
        }
        changed
    }
    pub fn update_tab_dynamic_title(&mut self, window_id: WindowId, tab_id: TabId, title: &str) {
        if let Some(window) = self.windows.iter_mut().find(|w| w.id == window_id) {
            if let Some(tab) = window.tabs.iter_mut().find(|t| t.id == tab_id) {
                tab.dynamic_title = title.to_string();
            }
        }
    }
}

impl WindowModel {
    pub fn active_tab(&self) -> &TabModel {
        &self.tabs[self.active_tab]
    }
}

impl TabModel {
    pub fn active_inner_id(&self) -> Option<InnerTabId> {
        self.root.find_inner_id_for_terminal(self.focus)
    }
    fn single_terminal_tab() -> (Self, TerminalId) {
        let terminal_id = TerminalId(Uuid::new_v4());
        let node_id = NodeId(Uuid::new_v4());
        let leaf = TerminalLeaf {
            node_id,
            terminal_id,
            title: String::from("Terminal"),
            title_flexible: true,
        };
        let tab = TabModel {
            id: TabId(Uuid::new_v4()),
            root: LayoutNode::Terminal(leaf),
            focus: terminal_id,
            title: String::from("Terminal"),
            title_flexible: true,
            dynamic_title: String::from("Terminal"),
        };
        (tab, terminal_id)
    }

    pub fn display_title(&self) -> String {
        if self.title_flexible {
            self.dynamic_title.clone()
        } else {
            self.title.clone()
        }
    }

    pub fn is_title_flexible(&self) -> bool {
        self.title_flexible
    }

    pub fn active_terminal(&self) -> TerminalId {
        match &self.root {
            LayoutNode::Tabs(group) => group.tabs[group.active].focus,
            _ => self.focus,
        }
    }

    pub fn collect_terminal_ids(&self, out: &mut Vec<TerminalId>) {
        self.root.collect_terminal_ids(out);
    }

    fn first_terminal_id(&self) -> Option<TerminalId> {
        self.root.first_terminal_id()
    }

    fn set_focus_terminal(&mut self, id: TerminalId) -> bool {
        if !self.contains_terminal(id) {
            return false;
        }
        match &mut self.root {
            LayoutNode::Tabs(group) => {
                if let Some((idx, inner)) = group
                    .tabs
                    .iter_mut()
                    .enumerate()
                    .find(|(_, inner)| inner.root.contains_terminal(id))
                {
                    let mut changed = false;
                    if group.active != idx {
                        group.active = idx;
                        changed = true;
                    }
                    if inner.focus != id {
                        inner.focus = id;
                        changed = true;
                    }
                    return changed;
                }
                false
            }
            _ => {
                if self.focus != id {
                    self.focus = id;
                    true
                } else {
                    false
                }
            }
        }
    }

    fn contains_terminal(&self, id: TerminalId) -> bool {
        self.root.contains_terminal(id)
    }

    fn replace_leaf_with_split(
        &mut self,
        target: TerminalId,
        orientation: SplitOrientation,
        new_terminal_id: TerminalId,
    ) -> bool {
        self.root
            .replace_leaf_with_split(target, orientation, new_terminal_id)
    }

    fn remove_terminal(&mut self, target: TerminalId) -> bool {
        self.root.remove_terminal(target)
    }

    fn is_empty(&self) -> bool {
        self.root.is_empty()
    }
}

#[cfg(any())]
impl LayoutNode {
    fn as_tabs_mut(&mut self) -> Option<&mut TabGroup> {
        match self {
            LayoutNode::Tabs(group) => Some(group),
            _ => None,
        }
    }

    fn collect_terminal_ids(&self, out: &mut Vec<TerminalId>) {
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

    fn first_terminal_id(&self) -> Option<TerminalId> {
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

    fn last_terminal_id(&self) -> Option<TerminalId> {
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

    

    // If there is a Tabs group that contains the target terminal, append a new inner tab to that group.
    // Returns true if a group was found and modified.
    fn add_inner_to_group_containing(
        &mut self,
        target: TerminalId,
        new_inner_id: InnerTabId,
        new_terminal_id: TerminalId,
    ) -> bool {
        match self {
            LayoutNode::Tabs(group) => {
                // Find the inner whose root contains target
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
                    // Recurse into inners
                    for inner in &mut group.tabs {
                        if inner
                            .root
                            .add_inner_to_group_containing(target, new_inner_id, new_terminal_id)
                        {
                            return true;
                        }
                    }
                    false
                }
            }
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.add_inner_to_group_containing(target, new_inner_id, new_terminal_id) {
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
    fn wrap_subtree_with_tabs_at(
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
                        // First inner: existing subtree
                        let first_terminal = existing.first_terminal_id().unwrap_or(orig_term);
                        let first_inner = InnerTab {
                            id: InnerTabId(Uuid::new_v4()),
                            title: String::from("Terminal"),
                            root: existing,
                            focus: first_terminal,
                            flexible: true,
                        };
                        // Second inner: the new terminal
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
                    if child.wrap_subtree_with_tabs_at(target, new_inner_id, new_terminal_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                // Find the inner containing the target and wrap inside it
                for inner in &mut group.tabs {
                    if inner.root.contains_terminal(target) {
                        if inner
                            .root
                            .wrap_subtree_with_tabs_at(target, new_inner_id, new_terminal_id)
                        {
                            // Keep the active as-is or set to the inner that was modified
                            // so UI reflects the change. Move focus inside parent Tabs handled by caller.
                            return true;
                        }
                    }
                }
                false
            }
        }
    }

    // Remove an inner tab by id anywhere in this subtree. Returns true if removed.
    fn remove_inner_by_id_recursive(&mut self, inner_id: InnerTabId) -> bool {
        match self {
            LayoutNode::Terminal(_) => false,
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.remove_inner_by_id_recursive(inner_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                if let Some(idx) = group.tabs.iter().position(|i| i.id == inner_id) {
                    group.tabs.remove(idx);
                    if group.tabs.is_empty() {
                        // Replace with an empty split placeholder; caller may collapse further.
                        *self = LayoutNode::Split(SplitNode {
                            node_id: NodeId(Uuid::new_v4()),
                            orientation: SplitOrientation::Vertical,
                            children: Vec::new(),
                        });
                    } else {
                        // Keep Tabs even when one inner remains; update active index accordingly
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
                        if inner.root.remove_inner_by_id_recursive(inner_id) {
                            return true;
                        }
                    }
                    false
                }
            }
        }
    }

    // Add a new inner tab to the Tabs group that contains the given inner id, using an existing
    // terminal id as the sole child of that new inner. Returns true if inserted.
    pub fn add_existing_terminal_to_group_by_inner_id(
        &mut self,
        target_inner: InnerTabId,
        moving_terminal_id: TerminalId,
    ) -> bool {
        match self {
            LayoutNode::Terminal(_) => false,
            LayoutNode::Split(split) => {
                for child in &mut split.children {
                    if child.add_existing_terminal_to_group_by_inner_id(target_inner, moving_terminal_id) {
                        return true;
                    }
                }
                false
            }
            LayoutNode::Tabs(group) => {
                // Is this the group that contains the target inner id?
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
                            .add_existing_terminal_to_group_by_inner_id(target_inner, moving_terminal_id)
                        {
                            return true;
                        }
                    }
                    false
                }
            }
        }
    }

    fn find_adjacent_terminal(
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
                        // Prefer adjacent lookup inside the containing child first; this
                        // makes nested splits of the same orientation behave as if merged.
                        if let Some(inner) = child.find_adjacent_terminal(target, orientation, forward) {
                            return Some(inner);
                        }
                        // Otherwise, fallback to sibling at this level when orientation matches
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

    fn replace_leaf_with_split(
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
                        // Order: keep existing first, then new one
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

    // Replace the target leaf with a split, using an existing terminal id as the new sibling.
    #[allow(dead_code)]
    fn replace_leaf_with_split_existing(
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

    /// Remove the terminal `target` from this subtree.
    ///
    /// Returns `true` if a terminal was removed anywhere under this node, `false` otherwise.
    fn remove_terminal(&mut self, target: TerminalId) -> bool {
        match self {
            // Leaf: remove only if it matches; otherwise nothing to do.
            LayoutNode::Terminal(leaf) => {
                if leaf.terminal_id == target {
                    // Replace the leaf with an empty split placeholder so callers can detect emptiness
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
                // First, attempt removal inside each child (do not drop children based on return values)
                for child in &mut split.children {
                    if child.remove_terminal(target) {
                        removed_any = true;
                    }
                }

                // Then, explicitly drop any terminal children that match the target (in case of direct children)
                split.children
                    .retain(|child| !matches!(child, LayoutNode::Terminal(leaf) if leaf.terminal_id == target));

                // Also drop any children that became empty as a result of recursive removals
                split.children.retain(|child| !child.is_empty());

                // Collapse degenerate split nodes
                match split.children.len() {
                    0 => {
                        // Entire split is empty now
                        // Keep as empty split; higher-level callers may collapse further
                    }
                    1 => {
                        let only = split.children.remove(0);
                        *self = only;
                    }
                    _ => {}
                }

                removed_any
            }
            LayoutNode::Tabs(group) => {
                // Find the inner that contains the target and attempt removal inside it
                if let Some(idx) = group
                    .tabs
                    .iter()
                    .enumerate()
                    .find_map(|(idx, inner)| if inner.root.contains_terminal(target) { Some(idx) } else { None })
                {
                    let inner = &mut group.tabs[idx];
                    let removed = inner.root.remove_terminal(target);
                    // If the inner became empty after removal, drop it and adjust active index
                    if inner.root.is_empty() {
                        group.tabs.remove(idx);
                        if group.tabs.is_empty() {
                            // Replace whole Tabs with an empty split placeholder
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

    fn is_empty(&self) -> bool {
        match self {
            LayoutNode::Terminal(_) => false,
            LayoutNode::Split(split) => split.children.is_empty(),
            LayoutNode::Tabs(group) => group.tabs.is_empty(),
        }
    }
}

impl InnerTab {
    pub fn display_title(&self) -> String {
        self.title.clone()
    }

    pub fn is_title_flexible(&self) -> bool {
        self.flexible
    }
}

fn default_keybindings() -> KeybindingMap {
    use ActionId::*;
    let mut map = KeybindingMap::new();
    map.insert(Copy, vec!["<Ctrl><Shift>C".into()]);
    map.insert(Paste, vec!["<Ctrl><Shift>V".into()]);
    map.insert(NewWindow, vec!["<Ctrl><Shift>N".into()]);
    map.insert(NewTab, vec!["<Ctrl><Shift>T".into()]);
    map.insert(NewInnerTab, vec!["<Ctrl><Shift>U".into()]);
    map.insert(SplitHorizontal, vec!["<Ctrl><Shift>E".into()]);
    map.insert(SplitVertical, vec!["<Ctrl><Shift>O".into()]);
    map.insert(Settings, vec!["<Ctrl><Shift>,".into()]);
    map.insert(Close, vec!["<Ctrl><Shift>W".into()]);
    map.insert(CloseInnerTab, vec!["<Ctrl><Shift>D".into()]);
    map.insert(FocusLeft, vec!["<Alt>Left".into()]);
    map.insert(FocusRight, vec!["<Alt>Right".into()]);
    map.insert(FocusUp, vec!["<Alt>Up".into()]);
    map.insert(FocusDown, vec!["<Alt>Down".into()]);
    map.insert(NextTab, vec!["<Ctrl>Page_Down".into()]);
    map.insert(PrevTab, vec!["<Ctrl>Page_Up".into()]);
    map
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup_workspace() -> (WorkspaceModel, WindowId, TabId, TerminalId) {
        let ws = WorkspaceModel::new_single_terminal();
        let window_id = ws.windows[0].id;
        let tab = &ws.windows[0].tabs[0];
        let tab_id = tab.id;
        let term_id = tab.active_terminal();
        (ws, window_id, tab_id, term_id)
    }

    #[test]
    fn add_inner_tab_creates_group_and_focuses_new() {
        let (mut ws, window_id, tab_id, term_id) = setup_workspace();
        assert!(matches!(
            ws.windows[0].tabs[0].root,
            LayoutNode::Terminal(_)
        ));

        let (_inner_id, new_terminal) = ws
            .add_inner_tab(window_id, tab_id, term_id)
            .expect("should add inner tab");

        // Should now be a Tabs group with 2 inner tabs
        match &ws.windows[0].tabs[0].root {
            LayoutNode::Tabs(group) => {
                assert_eq!(group.tabs.len(), 2);
                assert_eq!(group.active, 1);
            }
            other => panic!("expected Tabs group, got {:?}", other),
        }
        // Focus should be the new terminal id
        assert_eq!(ws.windows[0].tabs[0].active_terminal(), new_terminal);
    }

    #[test]
    fn split_and_collapse_on_close() {
        let (mut ws, window_id, _tab_id, first_term) = setup_workspace();
        // Split the only terminal
        let new_term = ws
            .split_terminal(window_id, first_term, SplitOrientation::Horizontal)
            .expect("split returns new terminal id");
        // After split, tree should be a Split with 2 children
        match &ws.windows[0].tabs[0].root {
            LayoutNode::Split(split) => {
                assert_eq!(split.children.len(), 2);
            }
            _ => panic!("expected Split after split_terminal"),
        }
        // Close the newly created terminal, should collapse back
        ws.close_terminal(window_id, new_term).expect("close ok");
        match &ws.windows[0].tabs[0].root {
            LayoutNode::Terminal(leaf) => {
                assert_eq!(leaf.terminal_id, first_term);
            }
            _ => panic!("expected Terminal after collapsing split"),
        }
    }

    #[test]
    fn close_inner_tabs_collapses_group() {
        let (mut ws, window_id, tab_id, term_id) = setup_workspace();
        let (_id2, _new_term) = ws.add_inner_tab(window_id, tab_id, term_id).expect("added");

        let inner_ids: Vec<InnerTabId> = match &ws.windows[0].tabs[0].root {
            LayoutNode::Tabs(group) => group.tabs.iter().map(|i| i.id).collect(),
            _ => panic!("expected tabs"),
        };

        // Close the new inner tab
        assert!(ws.close_inner_tab(window_id, tab_id, inner_ids[1]));
        match &ws.windows[0].tabs[0].root {
            LayoutNode::Tabs(group) => {
                assert_eq!(group.tabs.len(), 1);
            }
            _ => panic!("expected tabs after removing one inner tab"),
        }

        // Close the remaining inner tab -> removes the parent tab; workspace becomes empty window set
        assert!(ws.close_inner_tab(window_id, tab_id, inner_ids[0]));
        // Since this was the only tab in the window, the window is removed as well
        assert!(ws.windows.iter().all(|w| w.id != window_id));
    }

    #[test]
    fn close_terminal_removes_inner_tab_leaf() {
        let (mut ws, window_id, tab_id, term_id) = setup_workspace();
        let (_inner_id, new_term) = ws
            .add_inner_tab(window_id, tab_id, term_id)
            .expect("inner tab added");

        ws.close_terminal(window_id, new_term)
            .expect("closing inner tab terminal succeeds");

        match &ws.windows[0].tabs[0].root {
            LayoutNode::Tabs(group) => {
                assert_eq!(group.tabs.len(), 1);
                assert!(group.tabs[0].root.contains_terminal(term_id));
            }
            other => panic!("expected remaining tabs group, got {:?}", other),
        }
    }

    #[test]
    fn default_split_keybindings_match_expected() {
        let map = default_keybindings();
        let horiz = map
            .get(&ActionId::SplitHorizontal)
            .expect("horizontal binding exists");
        assert_eq!(horiz, &["<Ctrl><Shift>E".to_string()]);

        let vert = map
            .get(&ActionId::SplitVertical)
            .expect("vertical binding exists");
        assert_eq!(vert, &["<Ctrl><Shift>O".to_string()]);

        let next = map
            .get(&ActionId::NextTab)
            .expect("next tab binding exists");
        assert_eq!(next, &["<Ctrl>Page_Down".to_string()]);

        let prev = map
            .get(&ActionId::PrevTab)
            .expect("prev tab binding exists");
        assert_eq!(prev, &["<Ctrl>Page_Up".to_string()]);
    }

    #[test]
    fn focus_neighbor_across_splits() {
        let (mut ws, window_id, tab_id, first) = setup_workspace();
        let right = ws
            .split_terminal(window_id, first, SplitOrientation::Horizontal)
            .expect("horizontal split");

        assert_eq!(
            ws.focus_neighbor(window_id, tab_id, first, FocusDirection::Right),
            Some(right)
        );
        assert_eq!(
            ws.focus_neighbor(window_id, tab_id, right, FocusDirection::Left),
            Some(first)
        );

        let bottom = ws
            .split_terminal(window_id, right, SplitOrientation::Vertical)
            .expect("vertical split");

        assert_eq!(
            ws.focus_neighbor(window_id, tab_id, right, FocusDirection::Down),
            Some(bottom)
        );
        assert_eq!(
            ws.focus_neighbor(window_id, tab_id, bottom, FocusDirection::Up),
            Some(right)
        );
    }

    #[test]
    fn inner_tab_should_be_nested_in_lower_right_after_o_e_u() {
        // Sequence: Ctrl+Shift+O (vertical split), Ctrl+Shift+E (horizontal split on focused), Ctrl+Shift+U (new inner tab)
        let (mut ws, window_id, tab_id, first) = setup_workspace();

        // Split vertically: create right (or bottom) sibling; per implementation, new terminal becomes the second child
        let right_or_bottom = ws
            .split_terminal(window_id, first, SplitOrientation::Vertical)
            .expect("vertical split created");

        // Split horizontally on the newly created terminal to form a bottom-right quadrant
        let bottom_right = ws
            .split_terminal(window_id, right_or_bottom, SplitOrientation::Horizontal)
            .expect("horizontal split on new child");

        // Add inner tab at the currently focused terminal (should be bottom_right)
        let maybe = ws.add_inner_tab(window_id, tab_id, bottom_right);
        assert!(maybe.is_some());

        // Validate that the tabs node appears nested within the bottom-right branch, not at the top-level
        let root = &ws.windows[0].tabs[0].root;
        match root {
            LayoutNode::Split(outer) => {
                // Expect the second child branch to contain a split with a tabs node at its last child
                match &outer.children[outer.children.len() - 1] {
                    LayoutNode::Split(inner) => {
                        match &inner.children[inner.children.len() - 1] {
                            LayoutNode::Tabs(group) => {
                                assert!(group.tabs.len() >= 2, "expected at least two inner tabs");
                            }
                            other => panic!("expected nested tabs at bottom-right, got {:?}", other),
                        }
                    }
                    other => panic!("expected nested split as right/bottom branch, got {:?}", other),
                }
            }
            other => panic!("expected outer split as root, got {:?}", other),
        }
    }

    #[test]
    fn close_first_inner_tab_in_nested_group() {
        // Sequence: O (vertical), E (horizontal on new), U (new inner), then close first inner tab
        let (mut ws, window_id, tab_id, first) = setup_workspace();

        let right = ws
            .split_terminal(window_id, first, SplitOrientation::Vertical)
            .expect("vertical split created");

        let bottom_right = ws
            .split_terminal(window_id, right, SplitOrientation::Horizontal)
            .expect("horizontal split on right");

        let (_inner_id, _new_term) = ws
            .add_inner_tab(window_id, tab_id, bottom_right)
            .expect("inner tab added at bottom-right");

        // Locate nested group at bottom-right and capture the first inner id
        let first_inner_id = {
            let window = &ws.windows[0];
            let tab = &window.tabs[0];
            match &tab.root {
                LayoutNode::Split(outer) => match &outer.children[1] {
                    LayoutNode::Split(inner) => match inner.children.last().unwrap() {
                        LayoutNode::Tabs(group) => group.tabs.first().unwrap().id,
                        other => panic!("expected tabs node, got {:?}", other),
                    },
                    other => panic!("expected nested split on right, got {:?}", other),
                },
                other => panic!("expected split root, got {:?}", other),
            }
        };

        assert!(ws.close_inner_tab(window_id, tab_id, first_inner_id));

        // Verify there is still a Tabs group at bottom-right with exactly 1 inner tab
        let window = &ws.windows[0];
        let tab = &window.tabs[0];
        match &tab.root {
            LayoutNode::Split(outer) => match &outer.children[1] {
                LayoutNode::Split(inner) => match inner.children.last().unwrap() {
                    LayoutNode::Tabs(group) => assert_eq!(group.tabs.len(), 1),
                    other => panic!("expected tabs node after close, got {:?}", other),
                },
                other => panic!("expected nested right split after close, got {:?}", other),
            },
            other => panic!("expected split root after close, got {:?}", other),
        }

        // Ensure workspace still has one window and one top-level tab
        assert_eq!(ws.windows.len(), 1);
        assert_eq!(ws.windows[0].tabs.len(), 1);
    }

    #[test]
    fn closing_all_inner_tabs_removes_parent_tab_and_window() {
        let (mut ws, window_id, tab_id, term) = setup_workspace();
        let (_id2, _new_term) = ws
            .add_inner_tab(window_id, tab_id, term)
            .expect("inner added");
        // Now two inner tabs at top-level group
        let (id_a, id_b) = {
            let window = &ws.windows[0];
            let tab = &window.tabs[0];
            match &tab.root {
                LayoutNode::Tabs(group) => (group.tabs[0].id, group.tabs[1].id),
                other => panic!("expected tabs at top-level, got {:?}", other),
            }
        };
        assert!(ws.close_inner_tab(window_id, tab_id, id_a));
        assert!(ws.close_inner_tab(window_id, tab_id, id_b));
        // Removing last inner removes parent tab, which removes only tab -> window list empty
        assert!(ws.windows.is_empty());
    }

    #[test]
    fn focus_adjacent_in_nested_vertical_splits_moves_to_immediate_neighbor() {
        // Build nested vertical splits: A (top), then bottom split into B (top) and C (bottom).
        let (mut ws, window_id, tab_id, a) = setup_workspace();
        let b = ws
            .split_terminal(window_id, a, SplitOrientation::Vertical)
            .expect("split to create bottom");
        let c = ws
            .split_terminal(window_id, b, SplitOrientation::Vertical)
            .expect("split bottom into nested bottom");

        // From C, moving Up should go to B (immediate neighbor), not A.
        let up_from_c = ws
            .focus_neighbor(window_id, tab_id, c, FocusDirection::Up)
            .expect("up neighbor exists");
        assert_eq!(up_from_c, b, "expected immediate neighbor B when moving up from C");

        // From B, moving Down should go to C (immediate neighbor).
        let down_from_b = ws
            .focus_neighbor(window_id, tab_id, b, FocusDirection::Down)
            .expect("down neighbor exists");
        assert_eq!(down_from_b, c, "expected immediate neighbor C when moving down from B");
    }

    #[test]
    fn nested_vertical_behaves_as_flat_for_navigation() {
        // Same layout as above: ensure moving Up from C twice goes to A.
        let (mut ws, window_id, tab_id, a) = setup_workspace();
        let b = ws
            .split_terminal(window_id, a, SplitOrientation::Vertical)
            .expect("split to create bottom");
        let c = ws
            .split_terminal(window_id, b, SplitOrientation::Vertical)
            .expect("split bottom into nested bottom");

        let up1 = ws
            .focus_neighbor(window_id, tab_id, c, FocusDirection::Up)
            .expect("up neighbor exists");
        assert_eq!(up1, b);
        let up2 = ws
            .focus_neighbor(window_id, tab_id, up1, FocusDirection::Up)
            .expect("up neighbor exists");
        assert_eq!(up2, a, "second up should reach A as if the tree were flattened");
    }

    #[test]
    fn split_inside_double_nested_inner_tabs_succeeds() {
        // Build: split vertical to get right, split horizontal on right to get bottom-right.
        // Then add inner tabs at bottom-right, and again add inner tabs within that inner (double nested).
        // Now split the focused terminal (inside double-nested tabs) horizontally and expect success.
        let (mut ws, window_id, tab_id, first) = setup_workspace();
        let right = ws
            .split_terminal(window_id, first, SplitOrientation::Vertical)
            .expect("vsplit created");
        let bottom_right = ws
            .split_terminal(window_id, right, SplitOrientation::Horizontal)
            .expect("hsplit on right created");

        // Nest level 1 inner tabs
        let (_inner1, inner_term1) = ws
            .add_inner_tab(window_id, tab_id, bottom_right)
            .expect("inner level 1");
        // Focus is inner_term1 by contract of add_inner_tab; nest level 2 inside that
        let (_inner2, inner_term2) = ws
            .add_inner_tab(window_id, tab_id, inner_term1)
            .expect("inner level 2");

        // Attempt to split inner_term2 horizontally
        let new = ws.split_terminal(window_id, inner_term2, SplitOrientation::Horizontal);
        assert!(new.is_some(), "split should succeed inside nested inner tabs");

        // New terminal must be discoverable in the tree
        let window = &ws.windows[0];
        let tab = &window.tabs[0];
        let new_id = new.unwrap();
        assert!(tab.root.contains_terminal(new_id));
    }

    #[test]
    fn closing_all_terminals_in_one_tab_removes_that_tab() {
        // Start with a single window and one tab
        let (mut ws, window_id, _first_tab_id, first_term) = setup_workspace();

        // Build a 4-terminal layout in the first tab:
        // vertical split -> two branches; then split each branch horizontally.
        let right = ws
            .split_terminal(window_id, first_term, SplitOrientation::Vertical)
            .expect("vertical split created");
        let left_new = ws
            .split_terminal(window_id, first_term, SplitOrientation::Horizontal)
            .expect("left branch horizontal split");
        let right_new = ws
            .split_terminal(window_id, right, SplitOrientation::Horizontal)
            .expect("right branch horizontal split");

        // Add a second tab to ensure the window remains after removing the first tab
        let second_tab_id = ws
            .add_tab_to_window(window_id)
            .expect("second tab added");
        // Also give it a non-trivial layout so the window isn't empty by accident
        let second_first = ws
            .first_terminal_in_tab(window_id, second_tab_id)
            .expect("second tab first terminal");
        let second_right = ws
            .split_terminal(window_id, second_first, SplitOrientation::Vertical)
            .expect("second vertical split");
        let _ = ws
            .split_terminal(window_id, second_first, SplitOrientation::Horizontal)
            .expect("second left horizontal split");
        let _ = ws
            .split_terminal(window_id, second_right, SplitOrientation::Horizontal)
            .expect("second right horizontal split");

        // Now close all four terminals that belong to the first tab
        assert!(ws.close_terminal(window_id, left_new).is_some());
        assert!(ws.close_terminal(window_id, first_term).is_some());
        assert!(ws.close_terminal(window_id, right_new).is_some());
        assert!(ws.close_terminal(window_id, right).is_some());

        // The first tab should be removed; window must retain only the second tab
        assert_eq!(ws.windows.len(), 1, "window should remain present");
        let window = &ws.windows[0];
        assert_eq!(window.tabs.len(), 1, "closing last terminal must remove the tab");
        assert_eq!(window.tabs[0].id, second_tab_id, "remaining tab should be the second tab");
        assert!(window.tabs[0].root.first_terminal_id().is_some(), "remaining tab should have terminals");
    }
}

impl TabModel {
    fn ensure_tabs_group(&mut self) {
        // If already a tabs group, nothing to do
        if matches!(self.root, LayoutNode::Tabs(_)) {
            return;
        }
        // Otherwise, wrap current root into a first inner tab
        let old_root = std::mem::replace(
            &mut self.root,
            LayoutNode::Tabs(TabGroup {
                node_id: NodeId(Uuid::new_v4()),
                tabs: Vec::new(),
                active: 0,
            }),
        );
        if let LayoutNode::Tabs(group) = &mut self.root {
            let first_terminal = old_root.first_terminal_id().unwrap_or(self.focus);
            let inner = InnerTab {
                id: InnerTabId(Uuid::new_v4()),
                title: self.title.clone(),
                root: old_root,
                focus: first_terminal,
                flexible: self.title_flexible,
            };
            group.tabs.push(inner);
            group.active = 0;
        }
    }
}
