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
  error: string | null
}

declare module 'claude-code' {
  interface PluginState {
    waypoints: { snapshot: Snapshot | null; expanded: string[] }
  }
}
