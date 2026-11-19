import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Row, Snapshot } from '../types'

const PANE = 'waypoints'
const STYLE_PANE = 'waypoints-style'
const REFRESH_MS = 60_000
const MAX_TOP = 40
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

// 0.17.0 honest seat mapping. A mod cannot choose where a pane sits (Claude Code 2.1.327:
// `$.ui.open` takes no position; the surface seats it `dock` beside the transcript in the
// fullscreen layout from 110 columns, `inline` above the prompt otherwise, or as a desktop
// `widget`). So: left/right open the pane wherever the surface seats it (the engine picks the
// dock's side); top/bottom draw a one-line summary instead of a pane: under the logo notice
// (top, terminal, when the engine shows one) or under the prompt via `$.ui.status`. The pane is
// never drawn as a list above the prompt: seated inline it shows only its one-line form until
// the person clicks it (the never-sit rule).
const POSITIONS = ['top', 'bottom', 'left', 'right'] as const
type Position = (typeof POSITIONS)[number]

type GroupId = 'actionable' | 'gated' | 'waiting'
const GROUPS: readonly { id: GroupId; symbol: string; label: string }[] = [
  { id: 'actionable', symbol: '▶', label: 'Actionable' },
  { id: 'gated', symbol: '⛔', label: 'Gated' },
  { id: 'waiting', symbol: '⏳', label: 'Waiting' },
]

const snapshot = atom({ plugin: 'waypoints', key: 'snapshot' } as const, null)
const expanded = atom({ plugin: 'waypoints', key: 'expanded' } as const, [])
const groups = atom({ plugin: 'waypoints', key: 'groups' } as const, ['actionable'])
const compact = atom({ plugin: 'waypoints', key: 'compact' } as const, null)
const unplaced = atom({ plugin: 'waypoints', key: 'unplaced' } as const, false)

// The first InfoNotice text seen this load: `top` draws its line under that one notice only.
// A module variable on purpose — it starts over on a reload, as the notices are redrawn then.
let noticeText: string | null = null

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
  position: Snapshot['position'],
): Snapshot => ({
  display,
  style,
  position,
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
  const pos = await setting($, 'pane-position')
  const position: Position = POSITIONS.find(p => p === pos) ?? 'right'

  const ran = await cli($, ['list', '--open', '--json'])
  if (ran === null || ran.exitCode !== 0) {
    return failed(`waypoints.py exited ${ran?.exitCode ?? 'with an error'}`, display, style, position)
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
    const unpinned = (tier: string) =>
      rows.filter(i => !i.pinned && i.tier === tier).slice(0, MAX_TOP)

    return {
      display,
      style,
      position,
      open: doc.counts.open ?? rows.length,
      actionable: doc.counts.actionable ?? 0,
      gated: doc.counts.gated ?? 0,
      waiting: doc.counts.waiting ?? 0,
      untriaged: doc.counts.untriaged ?? 0,
      pinned: rows.filter(i => i.pinned).map(i => row(i)),
      top: rows
        .filter(i => !i.pinned && (i.tier === 'do-now' || i.tier === 'heavy'))
        .slice(0, MAX_TOP)
        .map(i => row(i)),
      gatedRows: unpinned('gated').map(i => row(i, i.gate_reason ? [`gate: ${i.gate_reason}`] : [])),
      waitingRows: unpinned('waiting').map(i => row(i, i.waiting_on ? [`waiting on: ${i.waiting_on}`] : [])),
      error: null,
    }
  } catch {
    return failed('could not parse waypoints.py output', display, style, position)
  }
}

// The status-line look: the one line the panel shrinks to, and the top/bottom summary.
const summaryText = (snap: Snapshot) =>
  snap.error !== null
    ? `waypoints: ${snap.error}`
    : `🧭 ${snap.open} open · ▶ ${snap.actionable} · ⛔ ${snap.gated} · ⏳ ${snap.waiting}`

// Which one-line surface (if any) stands in for the pane, kept current on every refresh.
// Returns what it did, in the words /waypoints-pane reports.
const applyLine = async ($: EngineInterface): Promise<string> => {
  const snap = await read($, snapshot)
  if (snap === null || snap.display === 'banner') {
    $.ui.status(undefined)
    return 'waypoints not loaded yet'
  }
  const isLine = snap.position === 'top' || snap.position === 'bottom'
  if (!isLine && !(await read($, unplaced))) {
    $.ui.status(undefined)
    return ''
  }
  if (snap.position === 'top' && noticeText !== null) {
    $.ui.status(undefined)
    return 'One-line summary under the logo notice.'
  }
  $.ui.status(summaryText(snap))
  if (snap.position === 'top') {
    return 'No logo notice this session; one-line summary shown under the prompt instead.'
  }
  if (snap.position === 'bottom') {
    return 'One-line summary under the prompt (a mod cannot place anything below the statusline).'
  }
  return 'One-line summary shown under the prompt.'
}

const syncPlaced = async ($: EngineInterface) => {
  const panes = await $.ui.panes()
  const mine = panes.find(p => p.id === PANE)
  const isUnplaced = mine !== undefined && !mine.isPlaced
  if ((await read($, unplaced)) !== isUnplaced) {
    await update($, unplaced, () => isUnplaced)
  }
}

const refresh = async ($: EngineInterface) => {
  const next = await load($)
  await update($, snapshot, () => next)
  await syncPlaced($)
  await applyLine($)
}

const paneOpen = ($: EngineInterface, rows?: number) =>
  $.ui.open(rows === undefined ? { id: PANE, title: 'Waypoints' } : { id: PANE, title: 'Waypoints', rows })

// Opens the full pane wherever the surface seats it, and says honestly what that seat is.
const openPane = async ($: EngineInterface, isFullscreen: boolean | undefined): Promise<string> => {
  const r = await paneOpen($)
  await update($, unplaced, () => !r.isPlaced)
  const line = await applyLine($)
  if (!r.isPlaced) {
    return `No surface draws the panel here yet${'reason' in r && r.reason ? ` (${r.reason})` : ''}. ${line}`
  }
  return isFullscreen === true
    ? 'Waypoints panel docked beside the transcript — the engine picks the side; left and right behave the same.'
    : 'This layout has no side dock; the panel shows as a one-line row above the prompt (click it to expand).'
}

const closePane = async ($: EngineInterface): Promise<boolean> => {
  const panes = await $.ui.panes()
  if (!panes.some(p => p.id === PANE)) return false
  await $.ui.close({ id: PANE })
  await update($, unplaced, () => false)
  return true
}

// Moves the panel to a position: left/right = the pane; top/bottom = a one-line summary.
const moveTo = async ($: EngineInterface, pos: Position, isFullscreen: boolean | undefined) => {
  if (pos === 'left' || pos === 'right') {
    return openPane($, isFullscreen)
  }
  await closePane($)
  return applyLine($)
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
      description:
        'Toggle the waypoints panel; with top|bottom|left|right move it there (left/right = the panel, top/bottom = a one-line summary)',
    })
    await $.command.register({
      name: 'waypoints-style',
      description: 'Preview the six collapsed-row looks (waypoints.py config set pane-style <name>)',
    })
    await refresh($)
    const snap = await read($, snapshot)
    // 0.17.0: display != banner shows the queue at launch, at the configured position.
    if (snap !== null && snap.display !== 'banner') {
      await moveTo($, snap.position, undefined)
    }
    $.clock.every(REFRESH_MS, () => refresh($))

    return next(e)
  })

  on('command.run', { command: 'waypoints-pane' }, async ($, e) => {
    const arg = (e.args ?? '').trim().toLowerCase()
    const isFullscreen = e.presentation?.isFullscreen
    if (arg !== '') {
      const pos = POSITIONS.find(p => p === arg)
      if (pos === undefined) {
        return { text: `Unknown position '${arg}'. Use one of: ${POSITIONS.join(' | ')}.` }
      }
      await cli($, ['config', 'set', 'pane-position', pos])
      await refresh($)
      const msg = await moveTo($, pos, isFullscreen)

      return { text: `${msg} (saved as pane-position=${pos})` }
    }
    // No arg: toggle the full panel, at whatever seat the surface gives, for every position.
    if (await closePane($)) {
      await applyLine($)
      return { text: 'Waypoints panel closed.' }
    }
    await refresh($)

    return { text: await openPane($, isFullscreen) }
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

  // `top`: the one-line summary sits under the first logo notice (terminal only).
  on('ui.render', { component: 'InfoNotice' }, async ($, e, next) => {
    const drawn = await next(e)
    if (noticeText === null) {
      noticeText = e.props.text
      void applyLine($)
    }
    const snap = await read($, snapshot)
    if (
      snap === null ||
      snap.display === 'banner' ||
      snap.position !== 'top' ||
      e.props.text !== noticeText
    ) {
      return drawn
    }
    const { Box, Text } = $.ui.resolve(e)

    return (
      <Box flexDirection="column">
        {drawn}
        <Text dimColor>{summaryText(snap)}</Text>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const { Box, Button, Text } = ui
    const snap = await read($, snapshot)

    if (snap === null) {
      return <Text dimColor>Loading waypoints…</Text>
    }

    const placement = e.props.placement
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
      actionable: snap.top,
      gated: snap.gatedRows,
      waiting: snap.waitingRows,
    }
    const counts: Record<GroupId, number> = {
      actionable: snap.actionable,
      gated: snap.gated,
      waiting: snap.waiting,
    }
    // Rows a waypoint takes: its title, plus (when open) its bullets and id line.
    const cost = (r: Row) => (open.has(r.id) ? 2 + r.summary.length : 1)
    const visible = [...snap.pinned, ...GROUPS.flatMap(g => (shown.has(g.id) ? members[g.id] : []))]
    const fullRows = 3 + GROUPS.length + visible.reduce((n, r) => n + cost(r), 0)

    // One-line mode: chosen by the person, or (left to the seat) whenever the pane is not
    // docked — inline above the prompt it is never a list until the person clicks it.
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
    const fitted = GROUPS.map(g => ({ ...g, rows: shown.has(g.id) ? fit(members[g.id]) : [] }))
    const hidden = visible.length - pinned.length - fitted.reduce((n, g) => n + g.rows.length, 0)

    return (
      <Box flexDirection="column">
        {head}
        <Box key="all">
          <Button
            key="expand-all"
            label="Expand all"
            onPress={() => update($, expanded, () => visible.map(r => r.id))}
          />
          <Text> </Text>
          <Button
            key="collapse-all"
            label="Collapse all"
            onPress={() => update($, expanded, () => [])}
          />
        </Box>
        {pinned.length > 0 && <Text bold>📌 Pinned</Text>}
        {rowList(ui, snap.style, pinned, look, 'p')}
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
        {hidden > 0 && <Text dimColor>  … and {hidden} more (collapse some, or widen the pane)</Text>}
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
