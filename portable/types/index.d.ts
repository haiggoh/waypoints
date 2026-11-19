export type Row = { id: string; title: string; summary: string[]; isPinned: boolean }
export type Snapshot = {
  display: 'banner' | 'pane' | 'both'
  style: 'native' | 'secondary' | 'plain' | 'links' | 'dark' | 'static'
  position: 'top' | 'bottom' | 'left' | 'right'
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
      // one-line mode: true/false once the person chose, null = follow the seat
      // (inline above the prompt or a desktop widget => one line; dock => full)
      compact: boolean | null
      // the pane was asked for but no surface placed it: the summary line stands in
      unplaced: boolean
    }
  }
}
