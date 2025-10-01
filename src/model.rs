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
}

pub type KeybindingMap = HashMap<ActionId, Vec<String>>;

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
    pub node_id: NodeId,
    pub terminal_id: TerminalId,
    pub title: String,
    pub title_flexible: bool,
}

#[derive(Clone, Debug)]
pub struct SplitNode {
    pub node_id: NodeId,
    pub orientation: SplitOrientation,
    pub children: Vec<LayoutNode>,
}

#[derive(Clone, Debug)]
pub struct TabGroup {
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

    pub fn set_active_tab(&mut self, window_id: WindowId, tab_id: TabId) {
        if let Some(window) = self.windows.iter_mut().find(|w| w.id == window_id) {
            if let Some(idx) = window.tabs.iter().position(|t| t.id == tab_id) {
                window.active_tab = idx;
            }
        }
    }

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

    pub fn split_terminal(
        &mut self,
        window_id: WindowId,
        terminal_id: TerminalId,
        orientation: SplitOrientation,
    ) -> Option<TerminalId> {
        let window = self.windows.iter_mut().find(|w| w.id == window_id)?;
        let tab = window.tabs.iter_mut().find(|t| t.contains_terminal(terminal_id))?;
        let new_terminal_id = TerminalId(Uuid::new_v4());
        let replaced = tab.replace_leaf_with_split(terminal_id, orientation, new_terminal_id);
        if replaced {
            tab.set_focus_terminal(new_terminal_id);
            Some(new_terminal_id)
        } else {
            None
        }
    }

    pub fn close_terminal(
        &mut self,
        window_id: WindowId,
        terminal_id: TerminalId,
    ) -> Option<()> {
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

    pub fn add_inner_tab(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        _from_terminal: TerminalId,
    ) -> Option<(InnerTabId, TerminalId)> {
        let window = self.windows.iter_mut().find(|w| w.id == window_id)?;
        let tab = window.tabs.iter_mut().find(|t| t.id == tab_id)?;
        tab.ensure_tabs_group();
        let group = match &mut tab.root {
            LayoutNode::Tabs(group) => group,
            _ => unreachable!(),
        };

        let new_terminal_id = TerminalId(Uuid::new_v4());
        let inner_id = InnerTabId(Uuid::new_v4());
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
        tab.focus = new_terminal_id;
        Some((inner_id, new_terminal_id))
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
                if let Some(group) = tab.root.as_tabs_mut() {
                    if let Some(idx) = group.tabs.iter().position(|i| i.id == inner_id) {
                        group.tabs.remove(idx);
                        changed = true;
                        if group.tabs.is_empty() {
                            remove_parent_tab = true;
                        } else {
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
        self.root.replace_leaf_with_split(target, orientation, new_terminal_id)
    }

    fn remove_terminal(&mut self, target: TerminalId) -> bool {
        self.root.remove_terminal(target)
    }

    fn is_empty(&self) -> bool {
        self.root.is_empty()
    }
}

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

    fn contains_terminal(&self, id: TerminalId) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => leaf.terminal_id == id,
            LayoutNode::Split(split) => split.children.iter().any(|c| c.contains_terminal(id)),
            LayoutNode::Tabs(group) => group.tabs.iter().any(|i| i.root.contains_terminal(id)),
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
                if let Some(inner) = group.tabs.get_mut(group.active) {
                    inner.root.replace_leaf_with_split(target, orientation, new_terminal_id)
                } else {
                    false
                }
            }
        }
    }

    fn remove_terminal(&mut self, target: TerminalId) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => leaf.terminal_id != target, // handled by parent
            LayoutNode::Split(split) => {
                split.children.retain_mut(|child| {
                    match child {
                        LayoutNode::Terminal(leaf) => leaf.terminal_id != target,
                        _ => {
                            let kept = child.remove_terminal(target);
                            kept
                        }
                    }
                });
                // Collapse if only one child remains
                if split.children.len() == 1 {
                    let only = split.children.remove(0);
                    *self = only;
                }
                // Return true if any terminals remain
                !self.is_empty()
            }
            LayoutNode::Tabs(group) => {
                let maybe_idx = group
                    .tabs
                    .iter()
                    .enumerate()
                    .find_map(|(idx, inner)| {
                        if inner.root.contains_terminal(target) {
                            Some(idx)
                        } else {
                            None
                        }
                    });
                if let Some(idx) = maybe_idx {
                    let inner = &mut group.tabs[idx];
                    let kept = inner.root.remove_terminal(target);
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
                    kept
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
    map.insert(SplitHorizontal, vec!["<Ctrl><Shift>H".into()]);
    map.insert(SplitVertical, vec!["<Ctrl><Alt>V".into()]);
    map.insert(Settings, vec!["<Ctrl><Shift>,".into()]);
    map.insert(Close, vec!["<Ctrl><Shift>W".into()]);
    map.insert(CloseInnerTab, vec!["<Ctrl><Shift>E".into()]);
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
        assert!(matches!(ws.windows[0].tabs[0].root, LayoutNode::Terminal(_)));

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
        let (_id2, new_term) = ws
            .add_inner_tab(window_id, tab_id, term_id)
            .expect("added");

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
