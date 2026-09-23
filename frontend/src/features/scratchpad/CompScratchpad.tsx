import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import clsx from 'clsx'
import { api, unwrap, type BanIn, type EvaluateOut, type RulesetOut, type ScratchpadOut, type ShipOut, type SlotIn } from '@/lib/api/client'
import { useCanAddToLibrary, useCompMutations, useRulesets, useRulesetShips, useScratchpad, useScratchpadMutations } from '@/lib/api/hooks'
import { Badge, Button, Checkbox, Empty, ErrorText, Input, Mono, PageHeader, Panel, Select, Table, Textarea } from '@/components/ui'
import { HullInput } from '@/features/comps/HullInput'
import { capTone, sizeCounts } from '@/features/comps/format'
import { ViolationList, rowFlags } from '@/features/comps/ViolationList'
import { PointsView } from '@/features/points/PointsView'
import { usePageTitle } from '@/hooks/usePageTitle'

type SlotState = { type_id: number | null; is_flagship: boolean; has_links: boolean }

const emptySlot = (): SlotState => ({ type_id: null, is_flagship: false, has_links: false })
const SAVE_DELAY_MS = 400

/** Try ten hulls against a ruleset without saving a comp. Saved per member on the server, so leaving the page keeps it. */
export function CompScratchpad() {
  usePageTitle('Comp scratchpad')
  const rulesets = useRulesets()
  const saved = useScratchpad()
  const [code, setCode] = useState('')
  useEffect(() => {
    if (code || !rulesets.data?.length || saved.isLoading) return
    const remembered = saved.data?.ruleset
    const fallback = rulesets.data.find((r) => r.has_point_table)?.code ?? rulesets.data[0].code
    setCode(remembered && rulesets.data.some((r) => r.code === remembered) ? remembered : fallback)
  }, [code, rulesets.data, saved.data, saved.isLoading])
  const ruleset = rulesets.data?.find((r) => r.code === code)

  if (rulesets.isLoading || saved.isLoading) return <Empty>Loading…</Empty>
  if (rulesets.error) return <ErrorText error={rulesets.error} />
  if (saved.error) return <ErrorText error={saved.error} />
  if (!ruleset) return <Empty>No rulesets imported.</Empty>

  return (
    <div>
      <PageHeader
        title="Comp scratchpad"
        context={
          <>
            <Select value={code} onChange={(e) => setCode(e.target.value)} data-testid="scratchpad.ruleset">
              {rulesets.data!.map((r) => (
                <option key={r.code} value={r.code}>
                  {r.code}
                  {r.has_point_table ? '' : ' (no point table)'}
                </option>
              ))}
            </Select>
            <Mono>
              cap {ruleset.point_cap} {'·'} {ruleset.fielded_pilots} pilots {'·'} inflation {ruleset.inflation_enabled ? ruleset.inflation_mode : 'off'} {'·'} same hull max{' '}
              {ruleset.max_same_hull ?? '∞'}
            </Mono>
          </>
        }
      />
      {ruleset.has_point_table ? (
        <Editor key={ruleset.code} ruleset={ruleset} saved={saved.data} />
      ) : (
        <p className="text-warn">This ruleset has no point table; nothing to evaluate.</p>
      )}
    </div>
  )
}

function initialSlots(ruleset: RulesetOut, saved: ScratchpadOut | undefined): SlotState[] {
  const rows = saved?.ruleset === ruleset.code ? saved.slots : []
  return Array.from({ length: ruleset.fielded_pilots }, (_, i) => ({
    type_id: rows[i]?.type_id ?? null,
    is_flagship: rows[i]?.is_flagship ?? false,
    has_links: rows[i]?.has_links ?? false,
  }))
}

/** Split pasted text on newlines and commas and resolve each name against the ruleset's hulls. */
export function parseHullList(text: string, byName: Map<string, ShipOut>): { found: ShipOut[]; unknown: string[] } {
  const lower = new Map([...byName].map(([name, ship]) => [name.toLowerCase(), ship]))
  const found: ShipOut[] = []
  const unknown: string[] = []
  for (const raw of text.split(/[\n,]/)) {
    const name = raw.trim()
    if (!name) continue
    const ship = lower.get(name.toLowerCase())
    if (ship) found.push(ship)
    else unknown.push(name)
  }
  return { found, unknown }
}

function focusSlot(slotNo: number) {
  document.querySelector<HTMLInputElement>(`[data-testid="scratchpad.slot.${slotNo}.hull"]`)?.focus()
}

function Editor({ ruleset, saved }: { ruleset: RulesetOut; saved: ScratchpadOut | undefined }) {
  const code = ruleset.code
  const fielded = ruleset.fielded_pilots
  const navigate = useNavigate()
  const ships = useRulesetShips(code)
  const byName = useMemo(() => new Map((ships.data ?? []).map((s) => [s.name, s])), [ships.data])
  const byId = useMemo(() => new Map((ships.data ?? []).map((s) => [s.type_id, s])), [ships.data])
  const { save } = useScratchpadMutations()
  const { createComp } = useCompMutations()
  const canAdd = useCanAddToLibrary()

  const [slots, setSlots] = useState<SlotState[]>(() => initialSlots(ruleset, saved))
  const [bans, setBans] = useState<number[]>(() => (saved?.ruleset === code ? saved.bans : []))
  const [banText, setBanText] = useState('')
  const [result, setResult] = useState<EvaluateOut | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [unknown, setUnknown] = useState<string[]>([])
  const [moving, setMoving] = useState(false)

  // Save 400 ms after the last change, and right away when the tab is hidden or the page is left.
  const dirty = useRef(false)
  const latest = useRef({ slots, bans })
  latest.current = { slots, bans }
  const saveTimer = useRef<number | undefined>(undefined)
  const flush = () => {
    window.clearTimeout(saveTimer.current)
    if (!dirty.current) return
    dirty.current = false
    save.mutate({ ruleset: code, slots: latest.current.slots, bans: latest.current.bans })
  }
  const markDirty = () => {
    dirty.current = true
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(flush, SAVE_DELAY_MS)
  }
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === 'hidden') flush()
    }
    document.addEventListener('visibilitychange', onHide)
    return () => {
      document.removeEventListener('visibilitychange', onHide)
      flush()
    }
    // flush reads refs only; registering once per editor is what we want
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const payload = {
      slots: slots.map<SlotIn>((s, i) => ({ slot_no: i + 1, is_unique: false, ...s })),
      bans: bans.map<BanIn>((type_id) => ({ type_id, made_by_side: 'A' })),
    }
    const handle = setTimeout(async () => {
      try {
        setResult(unwrap(await api.POST('/api/rulesets/{code}/evaluate', { params: { path: { code } }, body: payload })))
        setError(null)
      } catch (e) {
        setError(e)
      }
    }, 150)
    return () => clearTimeout(handle)
  }, [code, slots, bans])

  const updateSlots = (next: SlotState[]) => {
    setSlots(next)
    markDirty()
  }
  const updateBans = (next: number[]) => {
    setBans(next)
    markDirty()
  }
  const update = (i: number, patch: Partial<SlotState>) => updateSlots(slots.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const fillNextEmpty = (type_id: number) => {
    const i = slots.findIndex((s) => s.type_id == null)
    if (i !== -1) update(i, { type_id })
  }
  const addBan = () => {
    const s = byName.get(banText.trim())
    if (s && !bans.includes(s.type_id)) updateBans([...bans, s.type_id])
    setBanText('')
  }
  const clearAll = () => {
    if (!window.confirm('Clear every slot and ban on the scratchpad?')) return
    setSlots(Array.from({ length: fielded }, emptySlot))
    setBans([])
    setUnknown([])
    dirty.current = true
    latest.current = { slots: Array.from({ length: fielded }, emptySlot), bans: [] }
    flush()
  }
  const applyPaste = (text: string) => {
    const { found, unknown: missing } = parseHullList(text, byName)
    const next = slots.map(emptySlot)
    found.slice(0, fielded).forEach((ship, i) => {
      next[i] = { ...slots[i], type_id: ship.type_id }
    })
    updateSlots(next)
    setUnknown(missing)
    setPasteOpen(false)
    setPasteText('')
  }
  const paste = async () => {
    try {
      applyPaste(await navigator.clipboard.readText())
    } catch {
      setPasteOpen(true) // the browser refused; take the text by hand
    }
  }
  const filled = slots.filter((s) => s.type_id != null)
  const moveToComp = async () => {
    setMoving(true)
    try {
      // One request with the lineup: a refused lineup leaves no empty comp behind.
      const comp = await createComp.mutateAsync({
        name: `Scratchpad ${new Date().toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}`,
        ruleset: code,
        status: 'construction',
        notes: '',
        ban_theory: '',
        slots: slots.map((s, i) => ({ slot_no: i + 1, type_id: s.type_id, is_flagship: s.is_flagship, is_unique: false, ship_note: '', link_scripts: [] })),
      })
      await navigate({ to: '/comps/$compId', params: { compId: String(comp.id) } })
    } catch {
      // shown by <ErrorText error={createComp.error} />
    } finally {
      setMoving(false)
    }
  }

  const evalBySlot = new Map((result?.slots ?? []).map((s) => [s.slot_no, s]))
  const sizes = sizeCounts(ruleset, result)

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
      <div className="space-y-3">
        <Panel
          title="Comp"
          testId="scratchpad.comp"
          actions={
            <span className="flex items-center gap-1">
              <span className="mr-2 text-[11px] text-muted" data-testid="scratchpad.saved">
                {save.isPending ? 'Saving\u2026' : save.data?.updated_at ? `Saved ${new Date(save.data.updated_at).toLocaleTimeString(undefined, { timeStyle: 'short' })}` : ''}
              </span>
              <Button onClick={paste} data-testid="scratchpad.paste" title="one hull per line or comma separated">
                Paste hulls
              </Button>
              <Button onClick={clearAll} data-testid="scratchpad.clear" disabled={filled.length === 0 && bans.length === 0}>
                Clear all
              </Button>
              <Button variant="primary" onClick={moveToComp} data-testid="scratchpad.move" disabled={!canAdd || filled.length === 0 || moving} title={canAdd ? 'save as a construction comp and open the editor' : 'your role cannot add comps to the library'}>
                Move to comp editor
              </Button>
            </span>
          }
        >
          <ErrorText error={createComp.error ?? save.error} />
          {pasteOpen ? (
            <div className="mb-2 space-y-1" data-testid="scratchpad.paste.form">
              <Textarea rows={4} className="w-full" placeholder={'Astarte\nDeacon, Keres'} value={pasteText} onChange={(e) => setPasteText(e.target.value)} data-testid="scratchpad.paste.text" />
              <div className="flex gap-1">
                <Button variant="primary" onClick={() => applyPaste(pasteText)} data-testid="scratchpad.paste.apply">
                  Fill slots
                </Button>
                <Button variant="ghost" onClick={() => setPasteOpen(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
          <datalist id="scratchpad-hulls">{(ships.data ?? []).map((s) => <option key={s.type_id} value={s.name} />)}</datalist>
          <Table>
            <thead>
              <tr>
                <th>#</th>
                <th>Hull</th>
                <th>Class</th>
                <th>Size</th>
                {ruleset.flagship_enabled ? <th>Flag</th> : null}
                <th>Links</th>
                <th className="text-right">Pts</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {slots.map((slot, i) => {
                const ship = slot.type_id != null ? byId.get(slot.type_id) : undefined
                const ev = evalBySlot.get(i + 1)
                return (
                  <tr key={i} className={clsx(rowFlags(ev?.flags).length && 'bg-bad/10')}>
                    <td>
                      <Mono className="text-muted">{i + 1}</Mono>
                    </td>
                    <td>
                      <HullInput
                        value={ship?.name ?? ''}
                        lookup={byName}
                        listId="scratchpad-hulls"
                        onPick={(s) => update(i, { type_id: s?.type_id ?? null })}
                        testId={`scratchpad.slot.${i + 1}.hull`}
                        onEnter={() => focusSlot(i + 2)}
                        onArrow={(d) => focusSlot(i + 1 + d)}
                      />
                    </td>
                    <td className="text-muted">{ship?.ship_class ?? ''}</td>
                    <td>
                      <Mono>{ev?.effective_hull_size ?? ship?.hull_size ?? ''}</Mono>
                    </td>
                    {ruleset.flagship_enabled ? (
                      <td>
                        <Checkbox checked={slot.is_flagship} onChange={(e) => update(i, { is_flagship: e.target.checked })} data-testid={`scratchpad.slot.${i + 1}.flag`} />
                      </td>
                    ) : null}
                    <td>
                      <Checkbox checked={slot.has_links} onChange={(e) => update(i, { has_links: e.target.checked })} data-testid={`scratchpad.slot.${i + 1}.links`} />
                      {ev?.link_index ? <Mono className="ml-1 text-muted">L{ev.link_index}</Mono> : null}
                    </td>
                    <td className="text-right">
                      {ev && ev.type_id != null ? (
                        <Mono>
                          {ev.total_points}
                          {ev.inflation_points ? <span className="text-warn"> ({ev.base_points}+{ev.inflation_points})</span> : null}
                        </Mono>
                      ) : null}
                    </td>
                    <td>
                      <Mono className="text-bad">{rowFlags(ev?.flags).join(' ')}</Mono>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
          {unknown.length ? (
            <p className="mt-2 text-body text-warn" data-testid="scratchpad.paste.unknown">
              Not in this ruleset: {unknown.join(', ')}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-muted">Bans</span>
            <Input list="scratchpad-hulls" placeholder="hull name" value={banText} onChange={(e) => setBanText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addBan()} data-testid="scratchpad.bans.input" />
            <Button onClick={addBan} disabled={!byName.has(banText.trim())} data-testid="scratchpad.bans.add">
              Add ban
            </Button>
            {bans.map((id) => (
              <Button key={id} variant="ghost" className="line-through" onClick={() => updateBans(bans.filter((b) => b !== id))} title="remove">
                {byId.get(id)?.name ?? id}
              </Button>
            ))}
          </div>
        </Panel>
      </div>

      <div className="space-y-4">
        <Panel title="Evaluation" testId="scratchpad.eval">
          <ErrorText error={error} />
          {result ? (
            <div className="space-y-2">
              <div className="text-lg">
                <Mono testId="scratchpad.eval.total">
                  {result.total_points} / {result.point_cap}
                </Mono>{' '}
                <Badge tone={capTone(result.cap_status)} testId="scratchpad.eval.status">
                  {result.cap_status}
                  {result.cap_status === 'UNDER' ? ` (${result.unspent_points} unspent)` : ''}
                </Badge>{' '}
                <Badge tone={result.is_legal ? 'ok' : 'bad'} testId="scratchpad.eval.legal">
                  {result.is_legal ? 'legal' : 'illegal'}
                </Badge>
              </div>
              <div className="flex flex-wrap gap-1">
                {sizes.map((s) => (
                  <Badge key={s.size} tone={s.over ? 'bad' : s.count ? 'accent' : 'muted'}>
                    {s.size} {s.count}
                    {s.max != null ? `/${s.max}` : ''}
                  </Badge>
                ))}
              </div>
              <ViolationList violations={result.violations} slotCount={fielded} testId="scratchpad.eval.violations" />
            </div>
          ) : (
            <Empty>Fill a slot to evaluate.</Empty>
          )}
        </Panel>
        <Panel title="Points" testId="scratchpad.points">
          <PointsView code={code} compact onPick={(s) => fillNextEmpty(s.type_id)} />
        </Panel>
      </div>
    </div>
  )
}
