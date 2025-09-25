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

    pub fn terminals(&self, out: &mut Vec<TerminalId>) {
        match self {
            LayoutNode::Terminal(term) => out.push(term.terminal_id),
            LayoutNode::Split(split) => {
                split.children.iter().for_each(|child| child.terminals(out))
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

    pub fn active_tab_mut(&mut self) -> &mut TabModel {
        let index = self.active_tab;
        &mut self.tabs[index]
    }
}

#[derive(Clone, Debug, Default)]
pub struct WorkspaceModel {
    pub windows: Vec<WindowModel>,
}

impl WorkspaceModel {
    pub fn new_single_terminal() -> Self {
        let node_id = NodeId(Uuid::new_v4());
        let terminal_id = TerminalId(Uuid::new_v4());
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

        let window = WindowModel {
            id: window_id,
            title: String::from("Terminator 2"),
            tabs: vec![tab],
            active_tab: 0,
        };

        Self {
            windows: vec![window],
        }
    }

    pub fn window_mut(&mut self, id: WindowId) -> Option<&mut WindowModel> {
        self.windows.iter_mut().find(|w| w.id == id)
    }

    pub fn window(&self, id: WindowId) -> Option<&WindowModel> {
        self.windows.iter().find(|w| w.id == id)
    }
}
