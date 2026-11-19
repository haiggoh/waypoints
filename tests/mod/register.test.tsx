// Behavior tests for hooks/register.tsx on the real engine (`claude plugin test .`).
// Every hook a test adds with `on` stands for the engine beneath the plugin.
import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

type Opts = {
  display?: string
  position?: string
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
    'pane-position': o.position ?? 'top',
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
const lastStatus = (rec: { status: (string | undefined)[] }) => rec.status[rec.status.length - 1]

// ---- launch ---------------------------------------------------------------------------

test('display=pane, position=left opens the pane at launch', async ($, on) => {
  const rec = engine(on, { position: 'left' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.some(o => o.id === 'waypoints')).toBe(true)
})

test('display=banner opens nothing and sets no summary line', async ($, on) => {
  const rec = engine(on, { display: 'banner', position: 'left' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.length).toBe(0)
  expect(rec.status.every(s => s === undefined)).toBe(true)
})

// ---- honest seat mapping ----------------------------------------------------------------

test('bottom: no pane, the one-line summary under the prompt', async ($, on) => {
  const rec = engine(on, { position: 'bottom' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.length).toBe(0)
  expect(lastStatus(rec)).toBe('🧭 5 open · ▶ 2 · ⛔ 2 · ⏳ 1')
})

test('top with no logo notice: the summary falls back to under the prompt', async ($, on) => {
  const rec = engine(on, { position: 'top' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(rec.opens.length).toBe(0)
  expect(lastStatus(rec)).toBe('🧭 5 open · ▶ 2 · ⛔ 2 · ⏳ 1')
  const r = await pane($ as never, 'top')
  expect(r.text ?? '').toContain('No logo notice this session')
})

test('top with a logo notice: the summary is drawn under it and the status line cleared', async ($, on) => {
  const rec = engine(on, { position: 'top' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({
    plugin: 'waypoints',
    surface: 'terminal',
    component: 'InfoNotice',
    props: { text: 'model: opus', command: null },
  } as never)
  expect(await (ui as { find: (q: object) => Promise<{ text: string } | undefined> }).find({ type: 'Text', text: /🧭 5 open/ })).toBeDefined()
  expect(lastStatus(rec)).toBeUndefined()
})

test('/waypoints-pane bottom persists, closes an open pane, and says what it did', async ($, on) => {
  const rec = engine(on, { position: 'left' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const r = await pane($ as never, 'bottom')
  expect(rec.sets).toContainEqual(['pane-position', 'bottom'])
  expect(rec.closes).toBe(1)
  expect(r.text ?? '').toContain('cannot place anything below the statusline')
  expect(r.text ?? '').toContain('saved as pane-position=bottom')
})

test('/waypoints-pane left and right open the pane and say the layout has no side dock', async ($, on) => {
  const rec = engine(on, { position: 'bottom' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  for (const pos of ['left', 'right']) {
    const r = await pane($ as never, pos)
    expect(r.text ?? '').toMatch(/no side dock|engine picks the side/)
  }
  expect(rec.opens.filter(o => o.id === 'waypoints').length).toBe(2)
})

test('/waypoints-pane left in the fullscreen layout says the engine picks the dock side', async ($, on) => {
  engine(on, { position: 'bottom' })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const r = await pane($ as never, 'left', true)
  expect(r.text ?? '').toContain('engine picks the side; left and right behave the same')
})

test('unknown position is refused and nothing is saved', async ($, on) => {
  const rec = engine(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const r = await pane($ as never, 'middle')
  expect(r.text).toBe("Unknown position 'middle'. Use one of: top | bottom | left | right.")
  expect(rec.sets.length).toBe(0)
})

for (const position of ['top', 'bottom', 'left', 'right']) {
  test(`/waypoints-pane with no arg toggles the full pane (position=${position})`, async ($, on) => {
    const rec = engine(on, { position })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const wasOpen = rec.panes.some(p => p.id === 'waypoints')
    const first = await pane($ as never)
    expect(rec.panes.some(p => p.id === 'waypoints')).toBe(!wasOpen)
    const second = await pane($ as never)
    expect(rec.panes.some(p => p.id === 'waypoints')).toBe(wasOpen)
    expect([first.text, second.text]).toContain('Waypoints panel closed.')
  })
}

test('a pane no surface places leaves the queue visible as the summary line', async ($, on) => {
  const rec = engine(on, { position: 'left', isPlaced: false })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect(lastStatus(rec)).toBe('🧭 5 open · ▶ 2 · ⛔ 2 · ⏳ 1')
})

// ---- groups (spec 7-9), identical on terminal and desktop --------------------------------

for (const surface of SURFACES) {
  test(`group titles collapse and expand (${surface})`, async ($, on) => {
    engine(on, { position: 'left' })
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
    engine(on, { position: 'left', gated: 0, waiting: 0 })
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

  // ---- one-line mode (spec 10) + never-sit ------------------------------------------------

  test(`inline seat shows only the one-line summary until clicked (${surface})`, async ($, on) => {
    const rec = engine(on, { position: 'left' })
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
    const reopen = rec.opens[rec.opens.length - 1] ?? {}
    expect(reopen.id).toBe('waypoints')
    expect(Number(reopen.rows)).toBeGreaterThanOrEqual(3)
    expect(await ui.find({ key: 'group-actionable-title' })).toBeDefined()
    await ui.press({ key: 'collapse-one-line' })
    expect(rec.opens[rec.opens.length - 1]?.rows).toBe(1)
    expect(await ui.find({ key: 'one-line' })).toBeDefined()
    await ui.unmount()
  })

  test(`dock seat shows the full pane by default (${surface})`, async ($, on) => {
    engine(on, { position: 'left' })
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const ui = (await mountPane($ as never, surface, 'dock')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      unmount: () => Promise<void>
    }
    expect(await ui.find({ key: 'one-line' })).toBeUndefined()
    expect(await ui.find({ key: 'collapse-one-line' })).toBeDefined()
    await ui.unmount()
  })

  test(`a failed CLI read shows the error in both forms (${surface})`, async ($, on) => {
    engine(on, { position: 'left', listFails: true })
    await $.session.start({ cwd: '/', surface, isInteractive: true })
    const inline = (await mountPane($ as never, surface, 'inline')) as {
      find: (q: object) => Promise<{ text: string } | undefined>
      press: (t: { key: string }) => Promise<unknown>
      unmount: () => Promise<void>
    }
    expect((await inline.find({ key: 'one-line' }))?.text).toBe('waypoints: waypoints.py exited 3')
    await inline.press({ key: 'one-line' })
    expect(await inline.find({ text: /waypoints: waypoints.py exited 3/ })).toBeDefined()
    await inline.unmount()
  })
}

test('a desktop widget draws a glance line and no buttons', async ($, on) => {
  engine(on, { position: 'left' })
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
  engine(on, { position: 'left' })
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

