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
      // one-line mode: true/false once the person chose; null = follow the seat (0.19.0:
      // dock => full, inline/widget => one line)
      compact: boolean | null
      // true iff the MOD opened the pane at launch (not the person) — 0.19.0 uses it to close
      // an auto-opened pane where the surface will not dock it (display=banner)
      autoOpened: boolean
    }
  }
}
