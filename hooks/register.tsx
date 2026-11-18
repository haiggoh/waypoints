import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Row, Snapshot } from '../types'

const PANE = 'waypoints'
const REFRESH_MS = 60_000
const MAX_TOP = 40

const snapshot = atom({ plugin: 'waypoints', key: 'snapshot' } as const, null)
const expanded = atom({ plugin: 'waypoints', key: 'expanded' } as const, [])

type Item = {
  id: string
  title: string
  summary: string[]
  done: boolean
  tier: string | null
  pinned: boolean
}

const failed = (error: string, display: Snapshot['display']): Snapshot => ({
  display,
  open: 0,
  actionable: 0,
  gated: 0,
  waiting: 0,
  untriaged: 0,
  pinned: [],
  top: [],
  error,
})

// The store is read only through the bundled CLI (never the JSON file itself). The CLI is
// bin/ in the marketplace layout and scripts/ in the portable layout.
const cli = async ($: EngineInterface, args: string[]) => {
  let last: Awaited<ReturnType<EngineInterface['process']['run']>> | null = null
  for (const dir of ['bin', 'scripts']) {
    last = await $.process
      .run(['python3', `${$.plugin.root}/${dir}/waypoints.py`, ...args])
      .catch(() => null)
    if (last !== null && last.exitCode === 0) {
      return last
    }
  }

  return last
}

const load = async ($: EngineInterface): Promise<Snapshot> => {
  const mode = await cli($, ['config', 'get', 'display', '--raw'])
  const text = mode?.exitCode === 0 ? mode.stdout.trim() : 'banner'
  const display: Snapshot['display'] =
    text === 'pane' || text === 'both' ? text : 'banner'

  const ran = await cli($, ['list', '--open', '--json'])
  if (ran === null || ran.exitCode !== 0) {
    return failed(`waypoints.py exited ${ran?.exitCode ?? 'with an error'}`, display)
  }

  try {
    const doc = JSON.parse(ran.stdout) as {
      counts: Record<string, number>
      items: Item[]
    }
    const rows = doc.items.filter(i => !i.done)
    const row = (i: Item): Row => ({
      id: i.id,
      title: i.title,
      summary: i.summary ?? [],
      isPinned: i.pinned,
    })

    return {
      display,
      open: doc.counts.open ?? rows.length,
      actionable: doc.counts.actionable ?? 0,
      gated: doc.counts.gated ?? 0,
      waiting: doc.counts.waiting ?? 0,
      untriaged: doc.counts.untriaged ?? 0,
      pinned: rows.filter(i => i.pinned).map(row),
      top: rows
        .filter(i => !i.pinned && (i.tier === 'do-now' || i.tier === 'heavy'))
        .slice(0, MAX_TOP)
        .map(row),
      error: null,
    }
  } catch {
    return failed('could not parse waypoints.py output', display)
  }
}

const refresh = async ($: EngineInterface) => {
  const next = await load($)
  await update($, snapshot, () => next)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'waypoints-pane',
      description: 'Show the open waypoints queue in a pane',
    })
    await refresh($)
    const snap = await read($, snapshot)
    // display = banner keeps today's behaviour: no pane, no band, until /waypoints-pane.
    if (snap !== null && snap.display !== 'banner') {
      void $.ui.open({ id: PANE, title: 'Waypoints' })
    }
    $.clock.every(REFRESH_MS, () => refresh($))

    return next(e)
  })

  on('command.run', { command: 'waypoints-pane' }, async $ => {
    await refresh($)
    const { isPlaced } = await $.ui.open({ id: PANE, title: 'Waypoints' })

    return {
      text: isPlaced
        ? 'Waypoints pane opened.'
        : 'No surface draws a pane here; with display pane or both the band above the prompt shows the counts.',
    }
  })

  // A waypoints.py call from the model or the user changes the queue (or the display mode).
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (e.tool === 'Bash' && JSON.stringify(e).includes('waypoints')) {
      await refresh($)
    }

    return ran
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const snap = await read($, snapshot)
    if (e.props.hasSurvey || snap === null || snap.display === 'banner') {
      return next(e)
    }

    const { Box, Text } = $.ui.resolve(e)

    return (
      <Box>
        <Text dimColor>
          {snap.error !== null
            ? `waypoints: ${snap.error}`
            : `🧭 ${snap.open} open · ${snap.actionable} actionable · ${snap.gated} gated · ${snap.waiting} waiting`}
        </Text>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const snap = await read($, snapshot)

    if (snap === null) {
      return <Text dimColor>Loading waypoints…</Text>
    }
    if (snap.error !== null) {
      return <Text>waypoints: {snap.error}</Text>
    }

    const open = new Set(await read($, expanded))
    const columns = Math.max(30, e.viewport?.columns ?? 80)
    const cut = (text: string, indent = 0) =>
      text.length > columns - 6 - indent
        ? `${text.slice(0, columns - 7 - indent)}…`
        : text
    const toggle = (id: string) =>
      update($, expanded, list =>
        list.includes(id) ? list.filter(one => one !== id) : [...list, id],
      )
    const everyRow = [...snap.pinned, ...snap.top]

    // Rows a waypoint takes: its title, plus (when open) its bullets and id line.
    const cost = (r: Row) => (open.has(r.id) ? 2 + r.summary.length : 1)
    let left = Math.max(6, (e.viewport?.rows ?? 24) - 9)
    const fit = (rows: Row[]) => {
      const out: Row[] = []
      for (const r of rows) {
        if (left - cost(r) < 0 && out.length > 0) break
        left -= cost(r)
        out.push(r)
      }

      return out
    }
    const pinned = fit(snap.pinned)
    const top = fit(snap.top)
    const hidden = everyRow.length - pinned.length - top.length

    const line = (r: Row) => (
      <Box key={r.id} flexDirection="column" marginBottom="xs">
        <Button key={`row-${r.id}`} onPress={() => toggle(r.id)}>
          <Text>
            {open.has(r.id) ? '▾' : '▸'} {cut(r.title, 2)}
          </Text>
        </Button>
        {open.has(r.id) &&
          r.summary.map((s, n) => (
            <Text key={`${r.id}-s${n}`} dimColor>
              {'    • '}
              {cut(s, 6)}
            </Text>
          ))}
        {open.has(r.id) && (
          <Text dimColor>
            {'    id: '}
            {r.id}
          </Text>
        )}
      </Box>
    )

    return (
      <Box flexDirection="column">
        <Text bold>🧭 {snap.open} open waypoints</Text>
        <Box>
          <Button
            key="expand-all"
            label="Expand all"
            onPress={() => update($, expanded, () => everyRow.map(r => r.id))}
          />
          <Text> </Text>
          <Button
            key="collapse-all"
            label="Collapse all"
            onPress={() => update($, expanded, () => [])}
          />
        </Box>
        {pinned.length > 0 && <Text bold>📌 Pinned</Text>}
        {pinned.map(line)}
        <Text bold>▶ Actionable ({snap.actionable})</Text>
        {top.map(line)}
        {hidden > 0 && <Text dimColor>  … and {hidden} more (collapse some, or widen the pane)</Text>}
        <Text dimColor>
          ⛔ {snap.gated} gated · ⏳ {snap.waiting} waiting · {snap.untriaged} untriaged
        </Text>
      </Box>
    )
  })
}
