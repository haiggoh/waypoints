export type Row = { id: string; title: string; summary: string[]; isPinned: boolean }
export type Snapshot = {
  display: 'banner' | 'pane' | 'both'
  style: 'native' | 'secondary' | 'plain' | 'links' | 'dark' | 'static'
  open: number
  actionable: number
  gated: number
  waiting: number
  untriaged: number
  pinned: Row[]
  top: Row[]
  gatedRows: Row[]
  waitingRows: Row[]
  error: string | null
}

declare module 'claude-code' {
  interface PluginState {
    waypoints: {
      snapshot: Snapshot | null
      expanded: string[]
      // group titles currently expanded: 'actionable' | 'gated' | 'waiting'
      groups: string[]
      // one-line mode: true/false once the person chose; null = full (0.18.0: the pane
      // always opens full at every seat; one line only when the person collapses it)
      compact: boolean | null
    }
  }
}
