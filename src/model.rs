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
}

impl LayoutNode {
    pub fn id(&self) -> NodeId {
        match self {
            LayoutNode::Terminal(term) => term.id,
            LayoutNode::Split(split) => split.id,
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
