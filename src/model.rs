use std::collections::HashMap;
use uuid::Uuid;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct WindowId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct TabId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct NodeId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct TerminalId(pub Uuid);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct InnerTabId(pub Uuid);

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
    SplitHorizontal,
    SplitVertical,
    Settings,
    Close,
}

pub type KeybindingMap = HashMap<ActionId, Vec<String>>;

#[derive(Clone, Debug)]
pub enum LayoutNode {
    Terminal(TerminalLeaf),
    Split(SplitNode),
    Tabs(TabGroup),
}

impl LayoutNode {
    pub fn id(&self) -> NodeId {
        match self {
            LayoutNode::Terminal(term) => term.id,
            LayoutNode::Split(split) => split.id,
            LayoutNode::Tabs(tabs) => tabs.id,
        }
    }

    pub fn close(&mut self, node_id: NodeId) -> bool {
        match self {
            LayoutNode::Terminal(leaf) => leaf.id == node_id,
            LayoutNode::Split(split) => {
                let mut idx = 0;
                while idx < split.children.len() {
                    if split.children[idx].close(node_id) {
                        split.children.remove(idx);
                        split.ratios.remove(idx);
                    } else {
                        idx += 1;
                    }
                }

                match split.children.len() {
                    0 => true,
                    1 => {
                        let remaining = split.children.remove(0);
                        *self = remaining;
                        false
                    }
                    len => {
                        let weight = 1.0 / len as f32;
                        split.ratios = vec![weight; len];
                        false
                    }
                }
            }
            LayoutNode::Tabs(group) => {
                let mut idx = 0;
                while idx < group.tabs.len() {
                    if group.tabs[idx].root.close(node_id) {
                        group.tabs.remove(idx);
                    } else {
                        idx += 1;
                    }
                }

                match group.tabs.len() {
                    0 => true,
                    1 => {
                        let tab = group.tabs.remove(0);
                        *self = tab.root;
                        false
                    }
                    len => {
                        group.active = group.active.min(len - 1);
                        false
                    }
                }
            }
        }
    }
}

#[derive(Clone, Debug)]
pub struct TerminalLeaf {
    pub id: NodeId,
    pub terminal_id: TerminalId,
    pub title_flexible: bool,
}

#[derive(Clone, Debug)]
pub struct SplitNode {
    pub id: NodeId,
    pub orientation: SplitOrientation,
    pub children: Vec<LayoutNode>,
    pub ratios: Vec<f32>,
}

#[derive(Clone, Debug)]
pub struct TabGroup {
    pub id: NodeId,
    pub tabs: Vec<InnerTab>,
    pub active: usize,
}

#[derive(Clone, Debug)]
pub struct InnerTab {
    pub id: InnerTabId,
    pub title: String,
    pub root: LayoutNode,
    pub active_terminal: TerminalId,
    pub title_flexible: bool,
}

#[derive(Clone, Debug)]
pub struct TabModel {
    pub id: TabId,
    pub title: String,
    pub root: LayoutNode,
    pub active_terminal: TerminalId,
    pub title_flexible: bool,
}

impl TabModel {
    pub fn active_terminal(&self) -> TerminalId {
        self.active_terminal
    }

    pub fn contains_terminal(&self, terminal_id: TerminalId) -> bool {
        node_contains(&self.root, terminal_id)
    }

    pub fn split_terminal(
        &mut self,
        target_id: TerminalId,
        orientation: SplitOrientation,
        split_id: NodeId,
        new_leaf: TerminalLeaf,
    ) -> bool {
        split_terminal_node(
            &mut self.root,
            target_id,
            orientation,
            split_id,
            LayoutNode::Terminal(new_leaf),
        )
    }

    pub fn remove_terminal(&mut self, terminal_id: TerminalId) -> Option<Option<TerminalId>> {
        if !self.contains_terminal(terminal_id) {
            return None;
        }

        let node_id = find_terminal_node(&self.root, terminal_id)?;

        if self.root.close(node_id) {
            return Some(None);
        }

        if self.active_terminal == terminal_id {
            if let Some(next) = self.first_terminal() {
                self.active_terminal = next;
                return Some(Some(next));
            }
            return Some(None);
        }

        Some(Some(self.active_terminal))
    }

    pub fn first_terminal(&self) -> Option<TerminalId> {
        first_terminal(&self.root)
    }

    pub fn collect_terminal_ids(&self, into: &mut Vec<TerminalId>) {
        collect_terminals(&self.root, into);
    }
}

#[derive(Clone, Debug)]
pub struct WindowModel {
    pub id: WindowId,
    pub title: String,
    pub tabs: Vec<TabModel>,
    pub active_tab: usize,
}

impl WindowModel {
    pub fn active_tab(&self) -> &TabModel {
        &self.tabs[self.active_tab]
    }

    pub fn active_tab_mut(&mut self) -> &mut TabModel {
        &mut self.tabs[self.active_tab]
    }

    pub fn set_active_tab(&mut self, tab_id: TabId) {
        if let Some(idx) = self.tabs.iter().position(|tab| tab.id == tab_id) {
            self.active_tab = idx;
        }
    }

    pub fn find_tab_index_containing(&self, terminal_id: TerminalId) -> Option<usize> {
        self.tabs
            .iter()
            .position(|tab| tab.contains_terminal(terminal_id))
    }
}

#[derive(Clone, Debug)]
pub struct WorkspaceModel {
    pub windows: Vec<WindowModel>,
    pub keybindings: KeybindingMap,
}

impl WorkspaceModel {
    pub fn new_single_terminal() -> Self {
        let mut workspace = Self {
            windows: Vec::new(),
            keybindings: default_keybindings(),
        };
        workspace.add_window();
        workspace
    }

    pub fn add_window(&mut self) -> WindowId {
        let window = Self::new_window_model();
        let id = window.id;
        self.windows.push(window);
        id
    }

    pub fn remove_window(&mut self, id: WindowId) {
        self.windows.retain(|w| w.id != id);
    }

    pub fn add_tab_to_window(&mut self, window_id: WindowId) -> Option<TabId> {
        let window = self
            .windows
            .iter_mut()
            .find(|window| window.id == window_id)?;

        let seq = window.tabs.len() + 1;
        let tab_id = TabId(Uuid::new_v4());
        let terminal_id = TerminalId(Uuid::new_v4());
        let node_id = NodeId(Uuid::new_v4());

        let leaf = TerminalLeaf {
            id: node_id,
            terminal_id,
            title_flexible: true,
        };

        let tab = TabModel {
            id: tab_id,
            title: format!("Tab {seq}"),
            root: LayoutNode::Terminal(leaf),
            active_terminal: terminal_id,
            title_flexible: true,
        };

        window.tabs.push(tab);
        window.active_tab = window.tabs.len() - 1;

        Some(tab_id)
    }

    pub fn split_terminal(
        &mut self,
        window_id: WindowId,
        terminal_id: TerminalId,
        orientation: SplitOrientation,
    ) -> Option<TerminalId> {
        let window = self
            .windows
            .iter_mut()
            .find(|window| window.id == window_id)?;

        let tab_index = window.find_tab_index_containing(terminal_id)?;
        let tab = &mut window.tabs[tab_index];

        let split_id = NodeId(Uuid::new_v4());
        let new_terminal_id = TerminalId(Uuid::new_v4());
        let new_node_id = NodeId(Uuid::new_v4());

        let leaf = TerminalLeaf {
            id: new_node_id,
            terminal_id: new_terminal_id,
            title_flexible: true,
        };

        if tab.split_terminal(terminal_id, orientation, split_id, leaf) {
            tab.active_terminal = new_terminal_id;
            window.active_tab = tab_index;
            Some(new_terminal_id)
        } else {
            None
        }
    }

    pub fn close_terminal(&mut self, window_id: WindowId, terminal_id: TerminalId) -> Option<()> {
        let window_index = self.windows.iter().position(|w| w.id == window_id)?;
        let mut remove_window = false;

        {
            let window = &mut self.windows[window_index];
            let tab_index = window.find_tab_index_containing(terminal_id)?;
            let tab = &mut window.tabs[tab_index];

            match tab.remove_terminal(terminal_id) {
                Some(None) => {
                    window.tabs.remove(tab_index);
                    if window.tabs.is_empty() {
                        remove_window = true;
                    } else {
                        window.active_tab = tab_index.min(window.tabs.len() - 1);
                        let active_tab = window.active_tab_mut();
                        if let Some(next) = active_tab.first_terminal() {
                            active_tab.active_terminal = next;
                        }
                    }
                }
                Some(Some(next_active)) => {
                    tab.active_terminal = next_active;
                    window.active_tab = tab_index;
                }
                None => return None,
            }
        }

        if remove_window {
            self.windows.remove(window_index);
        }

        Some(())
    }

    pub fn set_active_tab(&mut self, window_id: WindowId, tab_id: TabId) {
        if let Some(window) = self
            .windows
            .iter_mut()
            .find(|window| window.id == window_id)
        {
            window.set_active_tab(tab_id);
        }
    }

    pub fn set_active_terminal(
        &mut self,
        window_id: WindowId,
        tab_id: TabId,
        terminal_id: TerminalId,
    ) -> bool {
        if let Some(window) = self
            .windows
            .iter_mut()
            .find(|window| window.id == window_id)
        {
            if let Some(tab_index) = window.tabs.iter().position(|tab| tab.id == tab_id) {
                let contains = window.tabs[tab_index].contains_terminal(terminal_id);
                if contains {
                    let already_active_tab = window.active_tab == tab_index;
                    let already_active_terminal =
                        window.tabs[tab_index].active_terminal == terminal_id;
                    if already_active_tab && already_active_terminal {
                        return false;
                    }
                    window.tabs[tab_index].active_terminal = terminal_id;
                    window.set_active_tab(tab_id);
                    return true;
                }
            }
        }
        false
    }

    fn new_window_model() -> WindowModel {
        let terminal_id = TerminalId(Uuid::new_v4());
        let node_id = NodeId(Uuid::new_v4());
        let tab_id = TabId(Uuid::new_v4());
        let window_id = WindowId(Uuid::new_v4());

        let leaf = TerminalLeaf {
            id: node_id,
            terminal_id,
            title_flexible: true,
        };

        let tab = TabModel {
            id: tab_id,
            title: String::from("Tab 1"),
            root: LayoutNode::Terminal(leaf),
            active_terminal: terminal_id,
            title_flexible: true,
        };

        WindowModel {
            id: window_id,
            title: String::from("Terminator 2"),
            tabs: vec![tab],
            active_tab: 0,
        }
    }
}

fn node_contains(node: &LayoutNode, terminal_id: TerminalId) -> bool {
    match node {
        LayoutNode::Terminal(leaf) => leaf.terminal_id == terminal_id,
        LayoutNode::Split(split) => split
            .children
            .iter()
            .any(|child| node_contains(child, terminal_id)),
        LayoutNode::Tabs(group) => group
            .tabs
            .iter()
            .any(|tab| node_contains(&tab.root, terminal_id)),
    }
}

fn split_terminal_node(
    node: &mut LayoutNode,
    target_id: TerminalId,
    orientation: SplitOrientation,
    split_id: NodeId,
    new_child: LayoutNode,
) -> bool {
    match node {
        LayoutNode::Terminal(leaf) => {
            if leaf.terminal_id == target_id {
                let existing = leaf.clone();
                *node = LayoutNode::Split(SplitNode {
                    id: split_id,
                    orientation,
                    children: vec![LayoutNode::Terminal(existing), new_child],
                    ratios: vec![0.5, 0.5],
                });
                true
            } else {
                false
            }
        }
        LayoutNode::Split(split) => {
            for child in &mut split.children {
                if split_terminal_node(child, target_id, orientation, split_id, new_child.clone()) {
                    let weight = 1.0 / split.children.len() as f32;
                    split.ratios = vec![weight; split.children.len()];
                    return true;
                }
            }
            false
        }
        LayoutNode::Tabs(group) => {
            for tab in &mut group.tabs {
                if split_terminal_node(
                    &mut tab.root,
                    target_id,
                    orientation,
                    split_id,
                    new_child.clone(),
                ) {
                    if let Some(first) = first_terminal(&tab.root) {
                        tab.active_terminal = first;
                    }
                    return true;
                }
            }
            false
        }
    }
}

fn first_terminal(node: &LayoutNode) -> Option<TerminalId> {
    match node {
        LayoutNode::Terminal(leaf) => Some(leaf.terminal_id),
        LayoutNode::Split(split) => split
            .children
            .iter()
            .find_map(|child| first_terminal(child)),
        LayoutNode::Tabs(group) => group
            .tabs
            .get(group.active)
            .and_then(|tab| first_terminal(&tab.root)),
    }
}

fn collect_terminals(node: &LayoutNode, into: &mut Vec<TerminalId>) {
    match node {
        LayoutNode::Terminal(leaf) => into.push(leaf.terminal_id),
        LayoutNode::Split(split) => {
            for child in &split.children {
                collect_terminals(child, into);
            }
        }
        LayoutNode::Tabs(group) => {
            for tab in &group.tabs {
                collect_terminals(&tab.root, into);
            }
        }
    }
}

fn find_terminal_node(node: &LayoutNode, terminal_id: TerminalId) -> Option<NodeId> {
    match node {
        LayoutNode::Terminal(leaf) => {
            if leaf.terminal_id == terminal_id {
                Some(leaf.id)
            } else {
                None
            }
        }
        LayoutNode::Split(split) => split
            .children
            .iter()
            .find_map(|child| find_terminal_node(child, terminal_id)),
        LayoutNode::Tabs(group) => group
            .tabs
            .iter()
            .find_map(|tab| find_terminal_node(&tab.root, terminal_id)),
    }
}

pub fn default_keybindings() -> KeybindingMap {
    use ActionId::*;
    HashMap::from([
        (Copy, vec!["<Ctrl><Shift>C".into()]),
        (Paste, vec!["<Ctrl><Shift>V".into()]),
        (NewWindow, vec!["<Ctrl><Shift>N".into()]),
        (NewTab, vec!["<Ctrl><Shift>T".into()]),
        (SplitHorizontal, vec!["<Ctrl><Shift>O".into()]),
        (SplitVertical, vec!["<Ctrl><Shift>E".into()]),
        (Settings, vec!["<Ctrl><Shift>S".into()]),
        (Close, vec!["<Ctrl><Shift>W".into()]),
    ])
}
