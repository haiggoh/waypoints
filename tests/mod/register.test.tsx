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
  pinned?: number
  actionable?: number
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
  const pinnedItems = Array.from({ length: o.pinned ?? 0 }, (_, n) =>
    item(`p${n}`, 'do-now', { pinned: true }),
  )
  const actionableItems = Array.from({ length: o.actionable ?? 2 }, (_, n) =>
    item(`a${n}`, n === 1 ? 'heavy' : 'do-now'),
  )
  const items = [...pinnedItems, ...actionableItems, ...gated, ...waiting]

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
          actionable: actionableItems.length,
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

// ---- launch: seat-driven (0.19.0) --------------------------------------------------------
// display=banner (the default) opens the pane at launch but CLOSES it where the surface will
// not dock it — window mode and the desktop widget stay banner-only. display=pane|both keeps
// the pane at every seat.

test('display=pane opens the pane at launch in window mode and it stays open', async ($, on) => {
  const rec = engine(on) // default display=pane
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.some(o => o.id === 'waypoints')).toBe(true)
  const ui = (await mountPane($ as never, 'terminal', 'inline')) as { unmount: () => Promise<void> }
  expect(rec.closes).toBe(0)
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(true)
  await ui.unmount()
})

test('display=banner auto-opens then closes the pane on an inline seat (window mode)', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.some(o => o.id === 'waypoints')).toBe(true)
  const ui = (await mountPane($ as never, 'terminal', 'inline')) as { unmount: () => Promise<void> }
  await ui.unmount()
  expect(rec.closes).toBeGreaterThanOrEqual(1)
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(false)
  expect(rec.status.length).toBe(0) // 0.18.0 invariant: no status line ever
})

test('display=banner keeps the pane on a dock seat (fullscreen)', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = (await mountPane($ as never, 'terminal', 'dock')) as { unmount: () => Promise<void> }
  await ui.unmount()
  expect(rec.closes).toBe(0)
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(true)
})

test('display=banner closes an auto-opened desktop widget too', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const ui = (await mountPane($ as never, 'desktop', 'widget')) as { unmount: () => Promise<void> }
  await ui.unmount()
  expect(rec.closes).toBeGreaterThanOrEqual(1)
})

test('display=both keeps the pane open on an inline seat too (opt-in everywhere)', async ($, on) => {
  // QC-4: display=both must behave like pane (pane stays at every seat), not like banner.
  const rec = engine(on, { display: 'both' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.some(o => o.id === 'waypoints')).toBe(true)
  const ui = (await mountPane($ as never, 'terminal', 'inline')) as { unmount: () => Promise<void> }
  await ui.unmount()
  expect(rec.closes).toBe(0)
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(true)
})

test('a manual /waypoints-pane open in window mode stays open', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await pane($ as never) // closes the auto-opened one
  const second = await pane($ as never) // manual open
  expect(second.text).not.toBe('Waypoints panel closed.')
  const ui = (await mountPane($ as never, 'terminal', 'inline')) as { unmount: () => Promise<void> }
  await ui.unmount()
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(true)
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
  const opensAtLaunch = rec.opens.length // every display mode auto-opens at launch now
  for (const arg of ['bottom', 'top', 'left', 'right', 'middle', 'Bottom']) {
    const r = await pane($ as never, arg)
    expect(r.text).toBe('/waypoints-pane takes no argument (positions were removed in 0.18.0: '
      + 'Claude Code decides where a pane sits).')
  }
  expect(rec.sets.length).toBe(0)
  expect(rec.opens.length).toBe(opensAtLaunch) // refusals open nothing extra
})

test('/waypoints-pane with no argument toggles the panel', async ($, on) => {
  const rec = engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(true) // auto-opened at launch
  const first = await pane($ as never)
  expect(first.text).toBe('Waypoints panel closed.')
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(false)
  const second = await pane($ as never)
  expect(second.text).not.toBe('Waypoints panel closed.')
  expect(rec.panes.some(p => p.id === 'waypoints')).toBe(true)
})

test('a pane no surface places says so, and nothing else stands in', async ($, on) => {
  const rec = engine(on, { display: 'banner', isPlaced: false })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await pane($ as never) // close the auto-opened (unplaced) pane
  const r = await pane($ as never) // manual re-open reports the unplaced seat
  expect(r.text ?? '').toContain('No surface draws the panel here yet')
  expect(r.text ?? '').toContain('too narrow')
  expect(rec.status.length).toBe(0)
})

// ---- groups (spec 7-9), identical on terminal and desktop --------------------------------

for (const surface of SURFACES) {
  test(`all four groups (incl. Pinned) start collapsed; titles expand them (${surface})`, async ($, on) => {
    engine(on, { pinned: 2 })
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'dock')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      press: (t: { key: string }) => Promise<unknown>
      unmount: () => Promise<void>
    }
    expect((await ui.find({ key: 'group-pinned-title' }))?.text).toBe('▸ 📌 Pinned (2)')
    expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▸ ▶ Actionable (2)')
    expect((await ui.find({ key: 'group-gated-title' }))?.text).toBe('▸ ⛔ Gated (2)')
    expect((await ui.find({ key: 'group-waiting-title' }))?.text).toBe('▸ ⏳ Waiting (1)')
    expect(await ui.find({ text: /title a0/ })).toBeUndefined()
    expect(await ui.find({ text: /title p0/ })).toBeUndefined()
    await ui.press({ key: 'group-pinned-title' })
    expect((await ui.find({ key: 'group-pinned-title' }))?.text).toBe('▾ 📌 Pinned (2)')
    expect(await ui.find({ text: /title p0/ })).toBeDefined()
    await ui.press({ key: 'group-actionable-title' })
    expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
    expect(await ui.find({ text: /title a0/ })).toBeDefined()
    await ui.press({ key: 'group-gated-title' })
    expect((await ui.find({ key: 'group-gated-title' }))?.text).toBe('▾ ⛔ Gated (2)')
    expect(await ui.find({ text: /title g0/ })).toBeDefined()
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

  // ---- the seat decides the default height (0.19.0): dock = full, inline = one line --------

  test(`dock seat renders FULL by default (${surface})`, async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'dock')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      unmount: () => Promise<void>
    }
    expect(await ui.find({ key: 'one-line' })).toBeUndefined()
    expect(await ui.find({ key: 'collapse-one-line' })).toBeDefined()
    expect(await ui.find({ key: 'group-actionable-title' })).toBeDefined()
    await ui.unmount()
  })

  test(`inline seat renders COLLAPSED (one line) by default, press expands (${surface})`, async ($, on) => {
    const rec = engine(on)
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'inline')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      findAll: (q: object) => Promise<unknown[]>
      press: (t: { key: string }) => Promise<unknown>
      unmount: () => Promise<void>
    }
    expect((await ui.find({ key: 'one-line' }))?.text).toBe('🧭 5 open · ▶ 2 · ⛔ 2 · ⏳ 1')
    expect(await ui.find({ key: 'group-actionable-title' })).toBeUndefined()
    expect((await ui.findAll({ type: 'Button' })).length).toBe(1)
    await ui.press({ key: 'one-line' })
    expect(await ui.find({ key: 'group-actionable-title' })).toBeDefined()
    expect(Number(rec.opens[rec.opens.length - 1]?.rows)).toBeGreaterThanOrEqual(3)
    await ui.unmount()
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
    expect(await ui.find({ key: 'group-actionable-title' })).toBeDefined()
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

test('/waypoints-pane in window mode opens the collapsed one line and says so', async ($, on) => {
  engine(on, { display: 'banner' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await pane($ as never) // close the auto-opened pane
  const r = await pane($ as never, '', false) // window mode (main screen, not fullscreen)
  expect(r.text ?? '').toContain('above the prompt')
  expect(r.text ?? '').toContain('one line')
})

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
  expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▸ ▶ Actionable (2)')
  await ui.unmount()
})

test('stored 0.17 groups state ([actionable]) renders open, pinned group present and collapsed', async ($, on) => {
  // QC-4 / plan Review Focus 1: a stored groups value from before the pinned group existed
  // must render without crashing — Actionable open, Pinned simply collapsed.
  engine(on, { pinned: 2 })
  on('state.get', (_, e, next) =>
    (e as { key?: string }).key === 'groups'
      ? { value: { value: ['actionable'], version: 1 } }
      : next(e),
  )
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = (await mountPane($ as never, 'terminal', 'dock')) as {
    find: (q: object) => Promise<{ text: string } | undefined>
    unmount: () => Promise<void>
  }
  expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
  expect(await ui.find({ text: /title a0/ })).toBeDefined()
  expect((await ui.find({ key: 'group-pinned-title' }))?.text).toBe('▸ 📌 Pinned (2)')
  await ui.unmount()
})

// ---- Expand all / Collapse all (0.19.0 accordion) ---------------------------------------

test('Expand all opens closed Actionable and every row; other groups keep their state', async ($, on) => {
  engine(on, { pinned: 2 })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = (await mountPane($ as never, 'terminal', 'dock')) as {
    find: (q: object) => Promise<{ text: string } | undefined>
    press: (t: { key: string }) => Promise<unknown>
    unmount: () => Promise<void>
  }
  await ui.press({ key: 'expand-all' })
  // Actionable opened so the result is visible (Expand all is never a no-op)…
  expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
  expect(await ui.find({ text: /title a0/ })).toBeDefined()
  expect(await ui.find({ text: /point a0/ })).toBeDefined() // row bullets open
  // …other groups stay closed, but their rows got expanded-state — visible once opened
  expect((await ui.find({ key: 'group-pinned-title' }))?.text).toBe('▸ 📌 Pinned (2)')
  await ui.press({ key: 'group-pinned-title' })
  expect(await ui.find({ text: /title p0/ })).toBeDefined()
  expect(await ui.find({ text: /point p0/ })).toBeDefined()
  await ui.unmount()
})

test('the full actionable queue renders without truncation (no cap, no fit cut)', async ($, on) => {
  engine(on, { actionable: 60 })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = (await mountPane($ as never, 'terminal', 'dock')) as {
    find: (q: object) => Promise<{ text: string } | undefined>
    press: (t: { key: string }) => Promise<unknown>
    unmount: () => Promise<void>
  }
  await ui.press({ key: 'group-actionable-title' }) // open the group (starts collapsed)
  expect(await ui.find({ text: /title a0/ })).toBeDefined()
  expect(await ui.find({ text: /title a29/ })).toBeDefined()
  expect(await ui.find({ text: /title a59/ })).toBeDefined()
  expect(await ui.find({ text: /and \d+ more/ })).toBeUndefined()
  await ui.unmount()
})

test('Collapse all closes every row but touches no group', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = (await mountPane($ as never, 'terminal', 'dock')) as {
    find: (q: object) => Promise<{ text: string } | undefined>
    press: (t: { key: string }) => Promise<unknown>
    unmount: () => Promise<void>
  }
  await ui.press({ key: 'group-actionable-title' })
  await ui.press({ key: 'expand-all' })
  expect(await ui.find({ text: /point a0/ })).toBeDefined()
  await ui.press({ key: 'collapse-all' })
  expect(await ui.find({ text: /point a0/ })).toBeUndefined()
  expect((await ui.find({ key: 'group-actionable-title' }))?.text).toBe('▾ ▶ Actionable (2)')
  await ui.unmount()
})