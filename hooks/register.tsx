import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Row, Snapshot } from '../types'

const PANE = 'waypoints'
const STYLE_PANE = 'waypoints-style'
const REFRESH_MS = 60_000
// One-line mode expands back to at least this many body rows (spec item 10).
const MIN_ROWS = 3

type PaneStyle = Snapshot['style']
const STYLES: readonly PaneStyle[] = [
  'native',
  'secondary',
  'plain',
  'links',
  'dark',
  'static',
]

// 0.18.0: positions are gone — Claude Code decides where a pane sits (docked beside the
// transcript in the fullscreen layout from 110 columns, inline above the prompt otherwise,
// or a desktop widget). The mod never writes a status line; the pane opens full at every seat.
type GroupId = 'pinned' | 'actionable' | 'gated' | 'waiting'
const GROUPS: readonly { id: GroupId; symbol: string; label: string }[] = [
  { id: 'pinned', symbol: '📌', label: 'Pinned' },
  { id: 'actionable', symbol: '▶', label: 'Actionable' },
  { id: 'gated', symbol: '⛔', label: 'Gated' },
  { id: 'waiting', symbol: '⏳', label: 'Waiting' },
]

const snapshot = atom({ plugin: 'waypoints', key: 'snapshot' } as const, null)
const expanded = atom({ plugin: 'waypoints', key: 'expanded' } as const, [])
const groups = atom({ plugin: 'waypoints', key: 'groups' } as const, [])
const compact = atom({ plugin: 'waypoints', key: 'compact' } as const, null)
const autoOpened = atom({ plugin: 'waypoints', key: 'autoOpened' } as const, false)

type Item = {
  id: string
  title: string
  summary: string[]
  done: boolean
  tier: string | null
  pinned: boolean
  gate_reason?: string | null
  waiting_on?: string | null
}

type Ui = ReturnType<EngineInterface['ui']['resolve']>
type Look = {
  open: Set<string>
  flip: (id: string) => void
  cut: (text: string, indent?: number) => string
}

const failed = (
  error: string,
  display: Snapshot['display'],
  style: PaneStyle,
): Snapshot => ({
  display,
  style,
  open: 0,
  actionable: 0,
  gated: 0,
  waiting: 0,
  untriaged: 0,
  pinned: [],
  top: [],
  gatedRows: [],
  waitingRows: [],
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

const setting = async ($: EngineInterface, key: string) => {
  const ran = await cli($, ['config', 'get', key, '--raw'])

  return ran?.exitCode === 0 ? ran.stdout.trim() : ''
}

const load = async ($: EngineInterface): Promise<Snapshot> => {
  const mode = await setting($, 'display')
  const display: Snapshot['display'] =
    mode === 'pane' || mode === 'both' ? mode : 'banner'
  const picked = await setting($, 'pane-style')
  const style: PaneStyle = STYLES.find(s => s === picked) ?? 'plain'

  const ran = await cli($, ['list', '--open', '--json'])
  if (ran === null || ran.exitCode !== 0) {
    return failed(`waypoints.py exited ${ran?.exitCode ?? 'with an error'}`, display, style)
  }

  try {
    const doc = JSON.parse(ran.stdout) as {
      counts: Record<string, number>
      items: Item[]
    }
    const rows = doc.items.filter(i => !i.done)
    const row = (i: Item, why: string[] = []): Row => ({
      id: i.id,
      title: i.title,
      summary: [...(i.summary ?? []), ...why],
      isPinned: i.pinned,
    })
    const unpinned = (tier: string) => rows.filter(i => !i.pinned && i.tier === tier)

    return {
      display,
      style,
      open: doc.counts.open ?? rows.length,
      actionable: doc.counts.actionable ?? 0,
      gated: doc.counts.gated ?? 0,
      waiting: doc.counts.waiting ?? 0,
      untriaged: doc.counts.untriaged ?? 0,
      pinned: rows.filter(i => i.pinned).map(i => row(i)),
      top: rows
        .filter(i => !i.pinned && (i.tier === 'do-now' || i.tier === 'heavy'))
        .map(i => row(i)),
      gatedRows: unpinned('gated').map(i => row(i, i.gate_reason ? [`gate: ${i.gate_reason}`] : [])),
      waitingRows: unpinned('waiting').map(i => row(i, i.waiting_on ? [`waiting on: ${i.waiting_on}`] : [])),
      error: null,
    }
  } catch {
    return failed('could not parse waypoints.py output', display, style)
  }
}

// The one-line look the panel shrinks to (and the desktop widget's glance line).
const summaryText = (snap: Snapshot) =>
  snap.error !== null
    ? `waypoints: ${snap.error}`
    : `🧭 ${snap.open} open · ▶ ${snap.actionable} · ⛔ ${snap.gated} · ⏳ ${snap.waiting}`

const refresh = async ($: EngineInterface) => {
  const next = await load($)
  await update($, snapshot, () => next)
}

const paneOpen = ($: EngineInterface, rows?: number) =>
  $.ui.open(rows === undefined ? { id: PANE, title: 'Waypoints' } : { id: PANE, title: 'Waypoints', rows })

// Opens the pane wherever the surface seats it, and says honestly what that seat is.
// `auto` records whether the MOD (session.start) or the person (/waypoints-pane) opened it —
// the auto-opened pane closes itself where the surface will not dock it under display=banner.
const openPane = async ($: EngineInterface, isFullscreen: boolean | undefined, auto: boolean): Promise<string> => {
  await update($, autoOpened, () => auto)
  const r = await paneOpen($)
  if (!r.isPlaced) {
    return `No surface draws the panel here yet${'reason' in r && r.reason ? ` (${r.reason})` : ''}.`
  }
  return isFullscreen === true
    ? 'Waypoints panel docked beside the transcript (the engine picks the side).'
    : 'Waypoints panel opened above the prompt (one line; press it to expand).'
}

const closePane = async ($: EngineInterface): Promise<boolean> => {
  const panes = await $.ui.panes()
  if (!panes.some(p => p.id === PANE)) return false
  await $.ui.close({ id: PANE })
  return true
}

const setCompact = async ($: EngineInterface, isCompact: boolean, fullRows: number) => {
  await update($, compact, () => isCompact)
  // `rows` is honored only while the surface seats the pane inline; the dock ignores it.
  await paneOpen($, isCompact ? 1 : Math.max(MIN_ROWS, fullRows))
}

// One collapsed-row look per PaneStyle. `plain` (dim, chrome-free) is the default; the others
// stay selectable because a desktop draws any Button natively and tastes differ.
const rowList = (ui: Ui, style: PaneStyle, rows: Row[], look: Look, tag: string) => {
  const { Box, Button, Markdown, Text } = ui
  const mark = (r: Row) => (look.open.has(r.id) ? '▾' : '▸')
  const more = (r: Row) =>
    look.open.has(r.id)
      ? [
          ...r.summary.map((s, n) => (
            <Text key={`${tag}-${r.id}-s${n}`} dimColor>
              {'    • '}
              {look.cut(s, 6)}
            </Text>
          )),
          <Text key={`${tag}-${r.id}-id`} dimColor>
            {'    id: '}
            {r.id}
          </Text>,
        ]
      : []

  if (style === 'links') {
    const text = rows
      .map(r => {
        const link = `${mark(r)} [${look.cut(r.title, 2).replace(/[[\]]/g, '')}](https://waypoints.invalid/${r.id})`
        const bullets = look.open.has(r.id)
          ? [...r.summary.map(s => `  - ${look.cut(s, 6)}`), `  - id: ${r.id}`].join('\n')
          : ''

        return bullets === '' ? link : `${link}\n${bullets}`
      })
      .join('\n\n')

    return (
      <Markdown
        key={`${tag}-md`}
        text={text}
        onLinkPress={link => look.flip(link.href.split('/').pop() ?? '')}
      />
    )
  }

  return rows.map(r => {
    const title = (
      <Text>
        {mark(r)} {look.cut(r.title, 2)}
      </Text>
    )
    const key = `${tag}-b-${r.id}`
    const head =
      style === 'native' ? (
        <Button key={key} onPress={() => look.flip(r.id)}>
          {title}
        </Button>
      ) : style === 'secondary' ? (
        <Button key={key} variant="secondary" onPress={() => look.flip(r.id)}>
          {title}
        </Button>
      ) : style === 'dark' ? (
        <Box>
          <Button key={key} plain onPress={() => look.flip(r.id)}>
            {mark(r)}
          </Button>
          <Text> {look.cut(r.title, 4)}</Text>
        </Box>
      ) : style === 'static' ? (
        title
      ) : (
        <Button key={key} plain dimColor onPress={() => look.flip(r.id)}>
          {title}
        </Button>
      )

    return (
      <Box
        key={`${tag}-${r.id}`}
        flexDirection="column"
        marginBottom="xs"
        backgroundColor={style === 'dark' ? '#0b0b0b' : undefined}
        paddingX={style === 'dark' ? 1 : undefined}
      >
        {head}
        {more(r)}
      </Box>
    )
  })
}

const flipper = ($: EngineInterface) => (id: string) =>
  update($, expanded, list =>
    list.includes(id) ? list.filter(one => one !== id) : [...list, id],
  )

const flipGroup = ($: EngineInterface, id: GroupId) =>
  update($, groups, list =>
    list.includes(id) ? list.filter(one => one !== id) : [...list, id],
  )

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'waypoints-pane',
      description: 'Toggle the waypoints panel (Claude Code decides where it sits)',
    })
    await $.command.register({
      name: 'waypoints-style',
      description: 'Preview the six collapsed-row looks (waypoints.py config set pane-style <name>)',
    })
    await refresh($)
    const snap = await read($, snapshot)
    // Seat-aware launch (Playbook-seat-aware-pane-mod): the session.start event carries
    // the surface. Desktop apps (Claude desktop Code tab, ChatGPT desktop Codex mode
    // where mods run) get the pane ON by default at launch; the terminal TUI keeps it
    // opt-in — /waypoints-pane opens it on demand there. Under display=banner the first
    // render still closes an auto-opened pane where the surface will not dock it.
    if (snap !== null && e.surface === 'desktop') {
      await openPane($, undefined, true)
    }
    $.clock.every(REFRESH_MS, () => refresh($))

    return next(e)
  })

  on('command.run', { command: 'waypoints-pane' }, async ($, e) => {
    const arg = (e.args ?? '').trim()
    // 0.18.0: positions are gone — any argument is refused and NOTHING is saved.
    if (arg !== '') {
      return {
        text: '/waypoints-pane takes no argument (positions were removed in 0.18.0: '
          + 'Claude Code decides where a pane sits).',
      }
    }
    const isFullscreen = e.presentation?.isFullscreen
    // No arg: toggle the full panel, at whatever seat the surface gives.
    if (await closePane($)) {
      return { text: 'Waypoints panel closed.' }
    }
    await refresh($)

    return { text: await openPane($, isFullscreen, false) }
  })

  on('command.run', { command: 'waypoints-style' }, async $ => {
    await refresh($)
    const { isPlaced } = await $.ui.open({ id: STYLE_PANE, title: 'Waypoints looks' })

    return {
      text: isPlaced
        ? 'Look preview opened. Pick one with: waypoints.py config set pane-style <name>'
        : 'No surface draws a pane here.',
    }
  })

  // A waypoints.py call from the model or the user changes the queue (or a setting).
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (e.tool === 'Bash' && JSON.stringify(e).includes('waypoints')) {
      await refresh($)
    }

    return ran
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const { Box, Button, Text } = ui
    const snap = await read($, snapshot)

    if (snap === null) {
      return <Text dimColor>Loading waypoints…</Text>
    }

    const placement = e.props.placement
    // 0.19.0 seat-driven launch: under display=banner the pane auto-opened at launch to learn
    // its seat; where the surface will NOT dock it (inline above the prompt, desktop widget),
    // the printed banner stays the queue view and the pane closes itself on this first render.
    if (placement !== 'dock' && snap.display === 'banner' && (await read($, autoOpened))) {
      const panes = await $.ui.panes()
      if (panes.some(p => p.id === PANE)) void closePane($)
    }
    // A desktop widget is a glance: clicks may not reach it, so it carries no Button.
    if (placement === 'widget') {
      return <Text dimColor>{summaryText(snap)}</Text>
    }

    const open = new Set(await read($, expanded))
    const shown = new Set(await read($, groups))
    const columns = Math.max(30, e.viewport?.columns ?? 80)
    const look: Look = {
      open,
      flip: flipper($),
      cut: (text, indent = 0) =>
        text.length > columns - 6 - indent
          ? `${text.slice(0, columns - 7 - indent)}…`
          : text,
    }
    const members: Record<GroupId, Row[]> = {
      pinned: snap.pinned,
      actionable: snap.top,
      gated: snap.gatedRows,
      waiting: snap.waitingRows,
    }
    const counts: Record<GroupId, number> = {
      pinned: snap.pinned.length,
      actionable: snap.actionable,
      gated: snap.gated,
      waiting: snap.waiting,
    }
    // Rows a waypoint takes: its title, plus (when open) its bullets and id line.
    const cost = (r: Row) => (open.has(r.id) ? 2 + r.summary.length : 1)
    const visible = GROUPS.flatMap(g => (shown.has(g.id) ? members[g.id] : []))
    const fullRows = 3 + GROUPS.length + visible.reduce((n, r) => n + cost(r), 0)

    // One-line mode: chosen by the person, or (left to seat) at the inline seat above the
    // prompt — 0.19.0 dogfooding found the full list too obtrusive there. The dock is full.
    const isCompact = (await read($, compact)) ?? placement !== 'dock'
    if (isCompact) {
      return (
        <Button key="one-line" plain dimColor onPress={() => setCompact($, false, fullRows)}>
          <Text>{summaryText(snap)}</Text>
        </Button>
      )
    }

    const head = (
      <Box key="head">
        <Text bold>🧭 {snap.open} open waypoints</Text>
        <Text> </Text>
        <Button key="collapse-one-line" plain dimColor onPress={() => setCompact($, true, fullRows)}>
          <Text>Collapse to one line</Text>
        </Button>
      </Box>
    )
    if (snap.error !== null) {
      return (
        <Box flexDirection="column">
          {head}
          <Text>waypoints: {snap.error}</Text>
        </Box>
      )
    }

    // 0.19.0: no fit cut — every row of every open group renders, and the engine's own scroll
    // window over the pane body (SiteScroll, read-only) lets the person move through them.
    const fitted = GROUPS.map(g => ({ ...g, rows: shown.has(g.id) ? members[g.id] : [] }))

    return (
      <Box flexDirection="column">
        {head}
        <Box key="all">
          <Button
            key="expand-all"
            label="Expand all"
            onPress={() => {
              // Every row in EVERY group (open or closed) gets its bullets open, and the
              // Actionable group is opened so the result is visible — Expand all must never
              // look like a no-op. Other groups keep their closed state; their rows are
              // expanded-state too, visible once the person opens them.
              update($, expanded, () =>
                [...snap.pinned, ...snap.top, ...snap.gatedRows, ...snap.waitingRows].map(r => r.id))
              update($, groups, list => (list.includes('actionable') ? list : [...list, 'actionable']))
            }}
          />
          <Text> </Text>
          <Button
            key="collapse-all"
            label="Collapse all"
            onPress={() => update($, expanded, () => [])}
          />
        </Box>
        {fitted.map(g => (
          <Box key={`group-${g.id}`} flexDirection="column">
            <Button key={`group-${g.id}-title`} plain onPress={() => flipGroup($, g.id)}>
              <Text bold>
                {shown.has(g.id) ? '▾' : '▸'} {g.symbol} {g.label} ({counts[g.id]})
              </Text>
            </Button>
            {rowList(ui, snap.style, g.rows, look, g.id)}
          </Box>
        ))}
        {snap.untriaged > 0 && <Text dimColor>{snap.untriaged} untriaged</Text>}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: STYLE_PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const { Box, Text } = ui
    const snap = await read($, snapshot)
    const sample = (snap?.top ?? []).slice(0, 3)

    if (snap === null || sample.length === 0) {
      return <Text dimColor>No sample waypoints yet.</Text>
    }

    const columns = Math.max(30, e.viewport?.columns ?? 80)
    const look: Look = {
      open: new Set(await read($, expanded)),
      flip: flipper($),
      cut: (text, indent = 0) =>
        text.length > columns - 6 - indent
          ? `${text.slice(0, columns - 7 - indent)}…`
          : text,
    }

    return (
      <Box flexDirection="column">
        <Text dimColor>
          Press a row to expand it. Current: {snap.style}. Choose with: waypoints.py config set pane-style &lt;name&gt;
        </Text>
        {STYLES.map(style => (
          <Box key={`look-${style}`} flexDirection="column" marginTop="xs">
            <Text bold>
              {style}
              {style === 'plain' ? ' (default)' : ''}
              {style === snap.style ? '  ← in use' : ''}
            </Text>
            {rowList(ui, style, sample, look, `s-${style}`)}
          </Box>
        ))}
      </Box>
    )
  })
}
