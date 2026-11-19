// Behavior tests for hooks/register.tsx on the real engine (`claude plugin test .`).
// Every hook a test adds with `on` stands for the engine beneath the plugin.
// 0.18.0: the status-line summary and every pane position are GONE. `/waypoints-pane` is a
// plain open/close toggle, the pane opens FULL wherever the surface seats it, and the mod
// never calls `$.ui.status` — Claude Code decides where a pane sits.
import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

type Opts = {
  display?: string
  isPlaced?: boolean
  gated?: number
  waiting?: number
  listFails?: boolean
}

const item = (id: string, tier: string, extra: Record<string, unknown> = {}) => ({
  id,
  title: `title ${id}`,
  summary: [`point ${id}`],
  done: false,
  tier,
  pinned: false,
  ...extra,
})

// The fake engine: answers the CLI and the ui calls, and records what the plugin asked.
const engine = (on: On, o: Opts = {}) => {
  const rec = {
    opens: [] as Record<string, unknown>[],
    closes: 0,
    status: [] as (string | undefined)[],
    sets: [] as string[][],
    panes: [] as { id: string; title: string; isPlaced: boolean }[],
  }
  const settings: Record<string, string> = {
    display: o.display ?? 'pane',
    'pane-style': 'plain',
  }
  const gated = Array.from({ length: o.gated ?? 2 }, (_, n) =>
    item(`g${n}`, 'gated', { gate_reason: `needs ${n}` }),
  )
  const waiting = Array.from({ length: o.waiting ?? 1 }, (_, n) =>
    item(`w${n}`, 'waiting', { waiting_on: `x${n}` }),
  )
  const items = [item('a0', 'do-now'), item('a1', 'heavy'), ...gated, ...waiting]

  on('process.run', (_, e) => {
    const argv = e.argv
    const i = argv.findIndex(a => a.endsWith('waypoints.py'))
    const args = argv.slice(i + 1)
    if (args[0] === 'config' && args[1] === 'get') {
      return { value: { exitCode: 0, stdout: `${settings[args[2] ?? ''] ?? ''}\n`, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    if (args[0] === 'config' && args[1] === 'set') {
      rec.sets.push(args.slice(2))
      settings[args[2] ?? ''] = args[3] ?? ''
      return { value: { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    if (args[0] === 'list') {
      if (o.listFails) return { value: { exitCode: 3, stdout: '', stderr: 'boom', isStdoutTruncated: false, isStderrTruncated: false } }
      const doc = {
        counts: {
          open: items.length,
          actionable: 2,
          gated: gated.length,
          waiting: waiting.length,
          untriaged: 0,
        },
        items,
      }
      return { value: { exitCode: 0, stdout: JSON.stringify(doc), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    return { value: { exitCode: 1, stdout: '', stderr: 'unknown', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('ui.open', (_, e) => {
    rec.opens.push({ ...e })
    const isPlaced = o.isPlaced ?? true
    if (!rec.panes.some(p => p.id === e.id)) {
      rec.panes.push({ id: e.id, title: e.title ?? '', isPlaced })
    }
    return { value: isPlaced ? { isPlaced: true } : { isPlaced: false, reason: 'too narrow' } }
  })
  on('ui.close', (_, e) => {
    rec.closes += 1
    rec.panes = rec.panes.filter(p => p.id !== e.id)
    return { value: undefined }
  })
  on('ui.panes', () => ({ value: rec.panes.map(p => ({ ...p })) }) as never)
  on('ui.status', (_, e) => {
    rec.status.push(e.text)
    return { value: undefined }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  mock.clock(on)

  return rec
}

const PANE_PROPS = (placement: 'dock' | 'inline' | 'widget') =>
  ({
    title: 'Waypoints',
    isFocused: false,
    bodyColumns: 60,
    placement,
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  }) as const

const mountPane = (
  $: { ui: { mount: (t: never) => Promise<never> } },
  surface: 'terminal' | 'desktop',
  placement: 'dock' | 'inline' | 'widget',
) =>
  $.ui.mount({
    plugin: 'waypoints',
    surface,
    component: 'Pane',
    requestId: 'waypoints',
    props: PANE_PROPS(placement),
  } as never)

const SURFACES = ['terminal', 'desktop'] as const

// /waypoints-pane as the person types it, on the main-screen layout unless told otherwise.
const pane = (
  $: { command: { run: (e: never) => Promise<{ text?: string }> } },
  args = '',
  isFullscreen = false,
) =>
  $.command.run({
    command: 'waypoints-pane',
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen, columns: isFullscreen ? 160 : 100 },
  } as never)

// ---- launch ---------------------------------------------------------------------------

test('display=pane opens the pane at launch', async ($, on) => {
  const rec = engine(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.some(o => o.id === 'waypoints')).toBe(true)
})

test('display=banner opens nothing and sets no status line', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.length).toBe(0)
  expect(rec.status.length).toBe(0)
})

// ---- no status-line summary, ever (0.18.0 removed it) ----------------------------------

test('the mod never calls ui.status (launch, toggle, refresh)', async ($, on) => {
  const rec = engine(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await pane($ as never) // toggle it shut
  await pane($ as never) // toggle it open
  await pane($ as never, 'left') // an argument is refused, but must still set no status
  expect(rec.status.length).toBe(0)
})

// ---- /waypoints-pane is a plain toggle; any argument is refused ------------------------

test('/waypoints-pane with any argument is refused and nothing is saved', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  for (const arg of ['bottom', 'top', 'left', 'right', 'middle', 'Bottom']) {
    const r = await pane($ as never, arg)
    expect(r.text).toBe('/waypoints-pane takes no argument (positions were removed in 0.18.0: '
      + 'Claude Code decides where a pane sits).')
  }
  expect(rec.sets.length).toBe(0)
  expect(rec.opens.length).toBe(0)
})

test('/waypoints-pane with no argument toggles the panel', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const first = await pane($ as never)
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(true)
  const second = await pane($ as never)
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(false)
  expect(second.text).toBe('Waypoints panel closed.')
  expect(first.text).not.toBe('Waypoints panel closed.')
})

test('a pane no surface places says so, and nothing else stands in', async ($, on) => {
  const rec = engine(on, { display: 'banner', isPlaced: false })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const r = await pane($ as never)
  expect(r.text ?? '').toContain('No surface draws the panel here yet')
  expect(r.text ?? '').toContain('too narrow')
  expect(rec.status.length).toBe(0)
})

// ---- groups (spec 7-9), identical on terminal and desktop --------------------------------

for (const surface of SURFACES) {
  test(`group titles collapse and expand (${surface})`, async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'dock')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      press: (t: { key: string }) => Promise<unknown>
      unmount: () => Promise<void>
    }
    expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
    expect((await ui.find({ key: 'group-gated-title' }))?.text).toBe('▸ ⛔ Gated (2)')
    expect((await ui.find({ key: 'group-waiting-title' }))?.text).toBe('▸ ⏳ Waiting (1)')
    expect(await ui.find({ text: /title g0/ })).toBeUndefined()
    await ui.press({ key: 'group-gated-title' })
    expect((await ui.find({ key: 'group-gated-title' }))?.text).toBe('▾ ⛔ Gated (2)')
    expect(await ui.find({ text: /title g0/ })).toBeDefined()
    expect(await ui.find({ text: /title g1/ })).toBeDefined()
    await ui.press({ key: 'group-gated-title' })
    expect(await ui.find({ text: /title g0/ })).toBeUndefined()
    await ui.press({ key: 'group-actionable-title' })
    expect(await ui.find({ text: /title a0/ })).toBeUndefined()
    await ui.unmount()
  })

  test(`empty gated/waiting groups still show (0) and expand to nothing (${surface})`, async ($, on) => {
    engine(on, { gated: 0, waiting: 0 })
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'dock')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      press: (t: { key: string }) => Promise<unknown>
      unmount: () => Promise<void>
    }
    expect((await ui.find({ key: 'group-gated-title' }))?.text).toBe('▸ ⛔ Gated (0)')
    await ui.press({ key: 'group-gated-title' })
    expect((await ui.find({ key: 'group-gated-title' }))?.text).toBe('▾ ⛔ Gated (0)')
    expect((await ui.find({ key: 'group-waiting-title' }))?.text).toBe('▸ ⏳ Waiting (0)')
    await ui.unmount()
  })

  // ---- the pane opens FULL by default at every seat (0.18.0) ----------------------------

  test(`inline and dock seats both render FULL by default (${surface})`, async ($, on) => {
    const rec = engine(on)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    for (const placement of ['inline', 'dock'] as const) {
      const ui = (await mountPane($ as never, surface, placement)) as {
        find: (q: object) => Promise<{ text: string } | undefined>
        unmount: () => Promise<void>
      }
      // full: the collapse button and group titles are both there, the one-line row is not
      expect(await ui.find({ key: 'one-line' })).toBeUndefined()
      expect(await ui.find({ key: 'collapse-one-line' })).toBeDefined()
      expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
      await ui.unmount()
    }
    // never collapsed at launch: every open asked for the auto height, not one row
    expect(rec.opens.filter(o => o.id === 'waypoints').every(o => Number(o.rows ?? 0) !== 1)).toBe(true)
  })

  test(`collapse to one line then press expands back to full (${surface})`, async ($, on) => {
    const rec = engine(on)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'dock')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      press: (t: { key: string }) => Promise<unknown>
      unmount: () => Promise<void>
    }
    await ui.press({ key: 'collapse-one-line' })
    expect((await ui.find({ key: 'one-line' }))?.text).toBe('🧭 5 open · ▶ 2 · ⛔ 2 · ⏳ 1')
    expect(await ui.find({ key: 'group-actionable-title' })).toBeUndefined()
    expect(rec.opens[rec.opens.length - 1]?.rows).toBe(1)
    await ui.press({ key: 'one-line' })
    expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
    expect(Number(rec.opens[rec.opens.length - 1]?.rows)).toBeGreaterThanOrEqual(3)
    await ui.unmount()
  })

  test(`a failed CLI read shows the error in the pane (${surface})`, async ($, on) => {
    engine(on, { listFails: true })
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'dock')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      unmount: () => Promise<void>
    }
    expect(await ui.find({ text: /waypoints: waypoints\.py exited 3/ })).toBeDefined()
    await ui.unmount()
  })
}

test('a desktop widget draws a glance line and no buttons', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const ui = (await mountPane($ as never, 'desktop', 'widget')) as {
    find: (q: object) => Promise<{ text: string } | undefined>
    findAll: (q: object) => Promise<unknown[]>
    unmount: () => Promise<void>
  }
  expect(await ui.find({ type: 'Text', text: '🧭 5 open · ▶ 2 · ⛔ 2 · ⏳ 1' })).toBeDefined()
  expect((await ui.findAll({ type: 'Button' })).length).toBe(0)
  await ui.unmount()
})

test('state stored by 0.16 (only `expanded`) still renders with the new defaults', async ($, on) => {
  engine(on)
  // Only the 0.16 key is seeded; every other key reaches the kit's own state store.
  on('state.get', (_, e, next) =>
    (e as { key?: string }).key === 'expanded'
      ? { value: { value: ['a0'], version: 1 } }
      : next(e),
  )
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = (await mountPane($ as never, 'terminal', 'dock')) as {
    find: (q: object) => Promise<{ text: string } | undefined>
    unmount: () => Promise<void>
  }
  expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
  await ui.unmount()
})