import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import clsx from 'clsx'
import { api, unwrap, type CompOut, type CompSlotIn, type EvaluateOut, type FitSummaryOut, type SlotIn } from '@/lib/api/client'
import { useComp, useCompMutations, useCompVocab, useFits, useMe, useRulesets, useRulesetShips } from '@/lib/api/hooks'
import { Badge, Button, Checkbox, Empty, ErrorText, Field, Input, Mono, Panel, Select, Table, Textarea } from '@/components/ui'
import { num, severityTone, when } from '@/features/fits/format'
import { HullInput } from './HullInput'
import { COMP_STATUSES, capTone, compStatusTone, sizeCounts } from './format'

export function CompBuilderPage() {
  const { compId } = useParams({ strict: false }) as { compId?: string }
  const id = Number(compId)
  const comp = useComp(id)
  if (comp.isLoading) return <Empty>Loading…</Empty>
  if (comp.error) return <ErrorText error={comp.error} />
  if (!comp.data) return <Empty>Not found.</Empty>
  return <Builder key={comp.data.updated_at} comp={comp.data} />
}

type SlotState = {
  type_id: number | null
  is_flagship: boolean
  is_unique: boolean
  warp_in_km: number | null
  default_fit_id: number | null
  ship_note: string
  link_scripts: string[]
  show_scripts: boolean
}

function fromComp(comp: CompOut): SlotState[] {
  return comp.slots.map((s) => ({
    type_id: s.type_id,
    is_flagship: s.is_flagship,
    is_unique: s.is_unique,
    warp_in_km: s.warp_in_km,
    default_fit_id: s.default_fit_id,
    ship_note: s.ship_note,
    link_scripts: s.link_scripts,
    show_scripts: s.link_scripts.length > 0,
  }))
}

function Builder({ comp }: { comp: CompOut }) {
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_library)
  const navigate = useNavigate()
  const rulesets = useRulesets()
  const ruleset = rulesets.data?.find((r) => r.code === comp.ruleset)
  const ships = useRulesetShips(comp.ruleset)
  const fits = useFits({})
  const vocab = useCompVocab()
  const { patchComp, cloneComp } = useCompMutations()

  const byName = useMemo(() => new Map((ships.data ?? []).map((s) => [s.name, s])), [ships.data])
  const byId = useMemo(() => new Map((ships.data ?? []).map((s) => [s.type_id, s])), [ships.data])
  const fitsById = useMemo(() => new Map((fits.data ?? []).map((f) => [f.id, f])), [fits.data])
  const fitsByShip = useMemo(() => {
    const map = new Map<number, FitSummaryOut[]>()
    for (const f of fits.data ?? []) {
      const list = map.get(f.ship_id) ?? []
      list.push(f)
      map.set(f.ship_id, list)
    }
    const rank = (s: string) => (s === 'active' ? 0 : s === 'suggested' ? 1 : s === 'construction' ? 1 : 2)
    for (const list of map.values()) list.sort((a, b) => rank(a.status) - rank(b.status) || a.name.localeCompare(b.name))
    return map
  }, [fits.data])

  const [slots, setSlots] = useState<SlotState[]>(() => fromComp(comp))
  const [name, setName] = useState(comp.name)
  const [notes, setNotes] = useState(comp.notes)
  const [banTheory, setBanTheory] = useState(comp.ban_theory)
  const [archetypeId, setArchetypeId] = useState<number | null>(comp.archetype_id)
  const [evaluation, setEvaluation] = useState<EvaluateOut | null>(comp.evaluation_detail)
  const [evalError, setEvalError] = useState<unknown>(null)

  const hasLinks = (s: SlotState) => {
    const fit = s.default_fit_id != null ? fitsById.get(s.default_fit_id) : undefined
    return fit ? fit.has_links : s.link_scripts.length > 0
  }

  useEffect(() => {
    const payload = {
      slots: slots.map<SlotIn>((s, i) => ({ slot_no: i + 1, type_id: s.type_id, is_flagship: s.is_flagship, is_unique: s.is_unique, has_links: hasLinks(s) })),
      bans: [],
    }
    const handle = setTimeout(async () => {
      try {
        setEvaluation(unwrap(await api.POST('/api/rulesets/{code}/evaluate', { params: { path: { code: comp.ruleset } }, body: payload })))
        setEvalError(null)
      } catch (e) {
        setEvalError(e)
      }
    }, 150)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slots, fits.data, comp.ruleset])

  const update = (i: number, patch: Partial<SlotState>) => setSlots((prev) => prev.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const evalBySlot = new Map((evaluation?.slots ?? []).map((s) => [s.slot_no, s]))
  const dirty =
    name !== comp.name ||
    notes !== comp.notes ||
    banTheory !== comp.ban_theory ||
    archetypeId !== comp.archetype_id ||
    JSON.stringify(fromComp(comp).map(strip)) !== JSON.stringify(slots.map(strip))

  const save = () =>
    patchComp.mutate({
      id: comp.id,
      body: {
        name,
        notes,
        ban_theory: banTheory,
        archetype_id: archetypeId,
        slots: slots.map<CompSlotIn>((s, i) => ({
          slot_no: i + 1,
          type_id: s.type_id,
          is_flagship: s.is_flagship,
          is_unique: s.is_unique,
          warp_in_km: s.warp_in_km,
          default_fit_id: s.default_fit_id,
          ship_note: s.ship_note,
          link_scripts: s.link_scripts,
        })),
        reason: '',
      },
    })

  const clone = async () => {
    const copy = await cloneComp.mutateAsync({ id: comp.id })
    await navigate({ to: '/comps/$compId', params: { compId: String(copy.id) } })
  }

  const stats = useMemo(() => {
    const chosen = slots.map((s) => (s.default_fit_id != null ? fitsById.get(s.default_fit_id) : undefined)).filter((f): f is FitSummaryOut => Boolean(f))
    const withStats = chosen.filter((f) => f.stats_parse_ok)
    const speeds = withStats.map((f) => f.speed_ms).filter((v): v is number => v != null)
    return {
      fits: chosen.length,
      dps: withStats.reduce((a, f) => a + (f.dps ?? 0), 0),
      ehp: withStats.reduce((a, f) => a + (f.ehp_k ?? 0), 0),
      avg: speeds.length ? speeds.reduce((a, b) => a + b, 0) / speeds.length : null,
      min: speeds.length ? Math.min(...speeds) : null,
    }
  }, [slots, fitsById])

  const sizes = sizeCounts(ruleset, evaluation)
  const linkOptions = vocab.data?.link_scripts ?? []

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/comps" className="text-muted hover:underline">
          Comps
        </Link>
        <span className="text-muted">/</span>
        {comp.can_edit ? <Input className="w-64 font-semibold" value={name} onChange={(e) => setName(e.target.value)} /> : <span className="font-semibold">{comp.name}</span>}
        <Badge tone={compStatusTone(comp.status)}>{comp.status}</Badge>
        <Mono className="text-muted">{comp.ruleset}</Mono>
        <span className="text-[11px] text-muted">
          {comp.created_by_name ? `by ${comp.created_by_name}, ` : ''}updated {when(comp.updated_at)}
          {comp.reviewed_by_name ? `, reviewed by ${comp.reviewed_by_name}` : ''}
        </span>
        <span className="flex-1" />
        <Button onClick={clone} disabled={cloneComp.isPending}>
          Clone
        </Button>
        {comp.can_edit ? (
          <Button variant="primary" disabled={!dirty || patchComp.isPending} onClick={save}>
            Save
          </Button>
        ) : null}
      </div>
      <ErrorText error={patchComp.error ?? cloneComp.error} />
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Panel title="Lineup">
          <datalist id="builder-hulls">{(ships.data ?? []).map((s) => <option key={s.type_id} value={s.name} />)}</datalist>
          <Table>
            <thead>
              <tr>
                <th>#</th>
                <th>Hull</th>
                <th>Size</th>
                {comp.flagship_enabled ? <th>Flag</th> : null}
                <th>Uniq</th>
                <th>Warp</th>
                <th>Default fit</th>
                <th>Links</th>
                <th>Note</th>
                <th className="text-right">Pts</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {slots.map((slot, i) => {
                const ship = slot.type_id != null ? byId.get(slot.type_id) : undefined
                const ev = evalBySlot.get(i + 1)
                const options = slot.type_id != null ? fitsByShip.get(slot.type_id) ?? [] : []
                const fit = slot.default_fit_id != null ? fitsById.get(slot.default_fit_id) : undefined
                const showScripts = slot.show_scripts || (fit?.has_links ?? false)
                return (
                  <tr key={i} className={clsx(ev?.flags.length && 'bg-bad/10')}>
                    <td>
                      <Mono className="text-muted">{i + 1}</Mono>
                    </td>
                    <td>
                      {comp.can_edit ? (
                        <HullInput listId="builder-hulls" className="w-44" value={ship?.name ?? ''} lookup={byName} onPick={(s) => update(i, { type_id: s?.type_id ?? null, default_fit_id: null })} />
                      ) : (
                        ship?.name ?? <span className="text-muted">empty</span>
                      )}
                    </td>
                    <td>
                      <Mono>{ev?.effective_hull_size ?? ship?.hull_size ?? ''}</Mono>
                    </td>
                    {comp.flagship_enabled ? (
                      <td>
                        <Checkbox checked={slot.is_flagship} disabled={!comp.can_edit} onChange={(e) => update(i, { is_flagship: e.target.checked })} />
                      </td>
                    ) : null}
                    <td>
                      <Checkbox checked={slot.is_unique} disabled={!comp.can_edit} onChange={(e) => update(i, { is_unique: e.target.checked })} />
                    </td>
                    <td>
                      <Input type="number" className="w-16" min={0} max={1000} value={slot.warp_in_km ?? ''} readOnly={!comp.can_edit} onChange={(e) => update(i, { warp_in_km: e.target.value === '' ? null : Number(e.target.value) })} />
                    </td>
                    <td>
                      <Select value={slot.default_fit_id ?? ''} disabled={!comp.can_edit || slot.type_id == null} onChange={(e) => update(i, { default_fit_id: e.target.value === '' ? null : Number(e.target.value) })}>
                        <option value="">{options.length ? 'no default fit' : 'no fits for hull'}</option>
                        {options.map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.name}
                            {f.status !== 'active' ? ` (${f.status})` : ''}
                            {f.has_links ? ' ⟟' : ''}
                          </option>
                        ))}
                      </Select>
                      {fit && fit.status !== 'active' ? <Badge tone="warn">{fit.status}</Badge> : null}
                    </td>
                    <td>
                      {ev?.link_index ? <Mono className="text-accent">L{ev.link_index}</Mono> : null}
                      {showScripts ? (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {Array.from({ length: 5 }, (_, k) => (
                            <Select
                              key={k}
                              className="w-16"
                              value={slot.link_scripts[k] ?? ''}
                              disabled={!comp.can_edit}
                              onChange={(e) => {
                                const next = [...slot.link_scripts]
                                if (e.target.value === '') next.splice(k, 1)
                                else next[k] = e.target.value
                                update(i, { link_scripts: next.filter(Boolean) })
                              }}
                            >
                              <option value="">—</option>
                              {linkOptions.map((l) => (
                                <option key={l.code} value={l.code} disabled={slot.link_scripts.includes(l.code) && slot.link_scripts[k] !== l.code}>
                                  {l.code} {l.name}
                                </option>
                              ))}
                            </Select>
                          ))}
                        </div>
                      ) : comp.can_edit ? (
                        <Button variant="ghost" onClick={() => update(i, { show_scripts: true })}>
                          + scripts
                        </Button>
                      ) : null}
                    </td>
                    <td>
                      <Input className="w-40" value={slot.ship_note} readOnly={!comp.can_edit} placeholder="ship note" onChange={(e) => update(i, { ship_note: e.target.value })} />
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
                      <Mono className="text-bad">{ev?.flags.join(' ')}</Mono>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        </Panel>

        <div className="space-y-4">
          <Panel title="Budget">
            <ErrorText error={evalError} />
            {evaluation ? (
              <div className="space-y-2">
                <div className="text-lg">
                  <Mono>
                    {evaluation.total_points} / {evaluation.point_cap}
                  </Mono>{' '}
                  <Badge tone={capTone(evaluation.cap_status)}>
                    {evaluation.cap_status}
                    {evaluation.cap_status === 'UNDER' ? ` (${evaluation.unspent_points} unspent)` : ''}
                  </Badge>{' '}
                  <Badge tone={evaluation.is_legal ? 'ok' : 'bad'}>{evaluation.is_legal ? 'legal' : 'illegal'}</Badge>
                </div>
                <div className="flex flex-wrap gap-1">
                  {sizes.map((s) => (
                    <Badge key={s.size} tone={s.over ? 'bad' : s.count ? 'accent' : 'muted'}>
                      {s.size} {s.count}
                      {s.max != null ? `/${s.max}` : ''}
                    </Badge>
                  ))}
                </div>
                <ul className="space-y-1 text-[12px]">
                  {evaluation.violations.map((v, i) => (
                    <li key={i}>
                      <Badge tone={severityTone(v.severity)}>{v.code}</Badge> {v.message}
                      {v.slot_nos.length ? <Mono className="text-muted"> [{v.slot_nos.join(',')}]</Mono> : null}
                    </li>
                  ))}
                  {evaluation.violations.length === 0 ? <li className="text-muted">no violations</li> : null}
                </ul>
              </div>
            ) : (
              <Empty>{ruleset && !ruleset.has_point_table ? 'This ruleset has no point table.' : 'Evaluating…'}</Empty>
            )}
          </Panel>

          <Panel title="Stats from default fits" actions={<Mono className="text-muted">{stats.fits}/{slots.length} fits</Mono>}>
            <Table>
              <tbody>
                <tr>
                  <td className="text-muted">Total DPS</td>
                  <td className="text-right">
                    <Mono>{num(stats.dps)}</Mono>
                  </td>
                </tr>
                <tr>
                  <td className="text-muted">Total EHP</td>
                  <td className="text-right">
                    <Mono>{num(stats.ehp, 1)}k</Mono>
                  </td>
                </tr>
                <tr>
                  <td className="text-muted">Speed avg / min</td>
                  <td className="text-right">
                    <Mono>
                      {num(stats.avg)} / {num(stats.min)}
                    </Mono>
                  </td>
                </tr>
              </tbody>
            </Table>
          </Panel>

          <Panel title="Notes">
            <div className="space-y-2">
              <Field label="Archetype">
                <Select value={archetypeId ?? ''} disabled={!comp.can_edit} onChange={(e) => setArchetypeId(e.target.value === '' ? null : Number(e.target.value))}>
                  <option value="">none</option>
                  {(vocab.data?.archetypes ?? [])
                    .filter((a) => !a.is_retired || a.id === archetypeId)
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                        {a.is_retired ? ' (retired)' : ''}
                      </option>
                    ))}
                </Select>
              </Field>
              <Field label="Comp notes">
                <Textarea rows={4} value={notes} readOnly={!comp.can_edit} onChange={(e) => setNotes(e.target.value)} />
              </Field>
              <Field label="Ban theory">
                <Textarea rows={3} value={banTheory} readOnly={!comp.can_edit} onChange={(e) => setBanTheory(e.target.value)} />
              </Field>
            </div>
          </Panel>

          {canManage ? <StatusPanel comp={comp} /> : null}
        </div>
      </div>
    </div>
  )
}

function strip(s: SlotState) {
  return {
    type_id: s.type_id,
    is_flagship: s.is_flagship,
    is_unique: s.is_unique,
    warp_in_km: s.warp_in_km,
    default_fit_id: s.default_fit_id,
    ship_note: s.ship_note,
    link_scripts: s.link_scripts,
  }
}

function StatusPanel({ comp }: { comp: CompOut }) {
  const { patchComp } = useCompMutations()
  const [status, setStatus] = useState(comp.status)
  const [reason, setReason] = useState('')
  return (
    <Panel title="Status">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Status">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {COMP_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Reason">
          <Input className="w-56" value={reason} placeholder="goes to the audit log" onChange={(e) => setReason(e.target.value)} />
        </Field>
        <Button variant="primary" disabled={status === comp.status || patchComp.isPending} onClick={() => patchComp.mutate({ id: comp.id, body: { status, reason } })}>
          Apply
        </Button>
      </div>
      <ErrorText error={patchComp.error} />
    </Panel>
  )
}
