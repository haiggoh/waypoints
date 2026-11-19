import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Row, Snapshot } from '../types'

const PANE = 'waypoints'
const STYLE_PANE = 'waypoints-style'
const REFRESH_MS = 60_000
const MAX_TOP = 40

type PaneStyle = Snapshot['style']
const STYLES: readonly PaneStyle[] = [
  'native',
  'secondary',
  'plain',
  'links',
  'dark',
  'static',
]

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
  const position: Snapshot['position'] =
    pos === 'top' || pos === 'bottom' || pos === 'left' || pos === 'right' ? pos : 'top'

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
    const row = (i: Item): Row => ({
      id: i.id,
      title: i.title,
      summary: i.summary ?? [],
      isPinned: i.pinned,
    })

    return {
      display,
      style,
      position,
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
    return failed('could not parse waypoints.py output', display, style, position)
  }
}

const refresh = async ($: EngineInterface) => {
  const next = await load($)
  await update($, snapshot, () => next)
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

export const register: Register = on => {
// 0.17.0 seat mapping, from the user's spec: top = very top of the window (InfoNotice, terminal
// only — the only surface-drawn line above everything else); bottom = BELOW the statusline,
// never above the prompt input (that is what 'inline' pane would be — forbidden for bottom);
// left/right = the docked pane. Surfaces without a seat fall back to the pane default.
const POSITIONS = ['top', 'bottom', 'left', 'right'] as const
type Position = (typeof POSITIONS)[number]

// Opens (or moves) the panel at the configured position. Returns what the surface actually did.
const openAt = async ($: EngineInterface, pos: Position): Promise<string> => {
  const snap = await read($, snapshot)
  if (snap === null) return 'waypoints not loaded yet'
  if (pos === 'left' || pos === 'right') {
    const r = await $.ui.open({ id: PANE, title: 'Waypoints' })   // dock seat (side of transcript)
    return r.isPlaced ? `Waypoints panel at ${pos}.` : `No surface draws a side pane here; panel open undrawn.`
  }
  if (pos === 'bottom') {
    // below the statusline: a pinned status line is the only under-prompt surface, and it is
    // UNDER the prompt — wrong side. Use the dock pane as the below-statusline surface instead.
    const r = await $.ui.open({ id: PANE, title: 'Waypoints' })
    return r.isPlaced ? 'Waypoints panel docked below the statusline area.' : 'No surface draws a bottom pane here; panel open undrawn.'
  }
  // top: the InfoNotice line under the logo is the very-top surface (terminal only)
  $.ui.status(`🧭 ${snap.open} open · ${snap.actionable} actionable · ${snap.gated} gated · ${snap.waiting} waiting`)
  const r = await $.ui.open({ id: PANE, title: 'Waypoints' })
  return r.isPlaced ? 'Waypoints panel at top.' : 'Waypoints counts pinned at the very top (status line); panel open undrawn.'
}

const closePanel = async ($: EngineInterface): Promise<string> => {
  const panes = await $.ui.panes()
  if (panes.some(p => p.id === PANE && p.isPlaced)) {
    await $.ui.close({ id: PANE })
    return 'Waypoints panel closed.'
  }
  if (panes.some(p => p.id === PANE)) {
    await $.ui.close({ id: PANE })
    return 'Waypoints panel closed.'
  }
  return 'Waypoints panel is not open.'
}

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'waypoints-pane',
      description: 'Toggle the waypoints panel; with a position arg (top|bottom|left|right) open/move it there',
    })
    await $.command.register({
      name: 'waypoints-style',
      description: 'Preview the six collapsed-row looks (waypoints.py config set pane-style <name>)',
    })
    await refresh($)
    const snap = await read($, snapshot)
    // 0.17.0: display != banner opens the panel at launch (default), at the configured position.
    if (snap !== null && snap.display !== 'banner') {
      void openAt($, snap.position)
    }
    $.clock.every(REFRESH_MS, () => refresh($))

    return next(e)
  })

  on('command.run', { command: 'waypoints-pane' }, async ($, e) => {
    const arg = (e.args ?? '').trim().toLowerCase()
    if (arg !== '' && !(POSITIONS as readonly string[]).includes(arg)) {
      return { text: `Unknown position '${arg}'. Use one of: ${POSITIONS.join(' | ')}.` }
    }
    if (arg !== '') {
      // placement arg: persist it, then open/move the panel there
      await cli($, ['config', 'set', 'pane-position', arg])
      await refresh($)
      const msg = await openAt($, arg as Position)
      return { text: `${msg} (saved as pane-position=${arg})` }
    }
    // no arg: toggle
    const panes = await $.ui.panes()
    if (panes.some(p => p.id === PANE)) return { text: await closePanel($) }
    await refresh($)
    const snap = await read($, snapshot)
    return { text: await openAt($, snap?.position ?? 'top') }
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

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const snap = await read($, snapshot)
    // 0.17.0: the band row is suppressed when the panel is the top placement (the panel is the
    // queue UI then) so the list never renders twice; other positions keep the band row.
    if (e.props.hasSurvey || snap === null) {
      return next(e)
    }
    if (snap.display === 'banner') {
      return next(e)
    }
    if (snap.position === 'top') {
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
    const ui = $.ui.resolve(e)
    const { Box, Button, Text } = ui
    const snap = await read($, snapshot)

    if (snap === null) {
      return <Text dimColor>Loading waypoints…</Text>
    }
    if (snap.error !== null) {
      return <Text>waypoints: {snap.error}</Text>
    }

    const open = new Set(await read($, expanded))
    const columns = Math.max(30, e.viewport?.columns ?? 80)
    const look: Look = {
      open,
      flip: flipper($),
      cut: (text, indent = 0) =>
        text.length > columns - 6 - indent
          ? `${text.slice(0, columns - 7 - indent)}…`
          : text,
    }
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
        {rowList(ui, snap.style, pinned, look, 'p')}
        <Text bold>▶ Actionable ({snap.actionable})</Text>
        {rowList(ui, snap.style, top, look, 't')}
        {hidden > 0 && <Text dimColor>  … and {hidden} more (collapse some, or widen the pane)</Text>}
        <Text dimColor>
          ⛔ {snap.gated} gated · ⏳ {snap.waiting} waiting · {snap.untriaged} untriaged
        </Text>
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
