import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { api, unwrap, type BanIn, type EvaluateOut, type SlotIn } from '@/lib/api/client'
import { useRulesets, useRulesetShips } from '@/lib/api/hooks'
import { Badge, Button, Checkbox, Empty, ErrorText, Input, Mono, Panel, Select, Table } from '@/components/ui'
import { HullInput } from '@/features/comps/HullInput'

/** Utilitarian harness for the rules engine: pick a ruleset, fill slots, read the evaluation. */
export function CompScratchpad() {
  const rulesets = useRulesets()
  const [code, setCode] = useState('')
  useEffect(() => {
    if (!code && rulesets.data?.length) setCode(rulesets.data.find((r) => r.has_point_table)?.code ?? rulesets.data[0].code)
  }, [code, rulesets.data])
  const ruleset = rulesets.data?.find((r) => r.code === code)

  if (rulesets.isLoading) return <Empty>Loading rulesets…</Empty>
  if (rulesets.error) return <ErrorText error={rulesets.error} />
  if (!ruleset) return <Empty>No rulesets imported. Run import_ruleset.</Empty>

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className="text-muted">Ruleset</span>
        <Select value={code} onChange={(e) => setCode(e.target.value)}>
          {rulesets.data!.map((r) => (
            <option key={r.code} value={r.code}>
              {r.code}
              {r.has_point_table ? '' : ' (no point table)'}
            </option>
          ))}
        </Select>
        <Mono className="text-muted">
          cap {ruleset.point_cap} · {ruleset.fielded_pilots} pilots · inflation {ruleset.inflation_enabled ? ruleset.inflation_mode : 'off'} · same hull max{' '}
          {ruleset.max_same_hull ?? '∞'}
        </Mono>
      </div>
      {ruleset.has_point_table ? (
        <Editor key={ruleset.code} code={ruleset.code} fielded={ruleset.fielded_pilots} flagship={ruleset.flagship_enabled} />
      ) : (
        <p className="text-warn">This ruleset has no point table; nothing to evaluate.</p>
      )}
    </div>
  )
}

type SlotState = { type_id: number | null; is_flagship: boolean; has_links: boolean }

function Editor({ code, fielded, flagship }: { code: string; fielded: number; flagship: boolean }) {
  const ships = useRulesetShips(code)
  const byName = useMemo(() => new Map((ships.data ?? []).map((s) => [s.name, s])), [ships.data])
  const byId = useMemo(() => new Map((ships.data ?? []).map((s) => [s.type_id, s])), [ships.data])

  const [slots, setSlots] = useState<SlotState[]>(() => Array.from({ length: fielded }, () => ({ type_id: null, is_flagship: false, has_links: false })))
  const [bans, setBans] = useState<number[]>([])
  const [banText, setBanText] = useState('')
  const [result, setResult] = useState<EvaluateOut | null>(null)
  const [error, setError] = useState<unknown>(null)

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

  const addBan = () => {
    const s = byName.get(banText.trim())
    if (s && !bans.includes(s.type_id)) setBans([...bans, s.type_id])
    setBanText('')
  }
  const update = (i: number, patch: Partial<SlotState>) => setSlots((prev) => prev.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const evalBySlot = new Map((result?.slots ?? []).map((s) => [s.slot_no, s]))

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <div>
        <datalist id="hulls">{(ships.data ?? []).map((s) => <option key={s.type_id} value={s.name} />)}</datalist>
        <Table>
          <thead>
            <tr>
              <th>#</th>
              <th>Hull</th>
              <th>Class</th>
              <th>Size</th>
              {flagship ? <th>Flag</th> : null}
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
                <tr key={i} className={clsx(ev?.flags.length && 'bg-bad/10')}>
                  <td>
                    <Mono className="text-muted">{i + 1}</Mono>
                  </td>
                  <td>
                    <HullInput value={ship?.name ?? ''} lookup={byName} onPick={(s) => update(i, { type_id: s?.type_id ?? null })} />
                  </td>
                  <td className="text-muted">{ship?.ship_class ?? ''}</td>
                  <td>
                    <Mono>{ev?.effective_hull_size ?? ship?.hull_size ?? ''}</Mono>
                  </td>
                  {flagship ? (
                    <td>
                      <Checkbox checked={slot.is_flagship} onChange={(e) => update(i, { is_flagship: e.target.checked })} />
                    </td>
                  ) : null}
                  <td>
                    <Checkbox checked={slot.has_links} onChange={(e) => update(i, { has_links: e.target.checked })} />
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
                    <Mono className="text-bad">{ev?.flags.join(' ')}</Mono>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </Table>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-muted">Bans</span>
          <Input list="hulls" placeholder="hull name" value={banText} onChange={(e) => setBanText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addBan()} />
          <Button onClick={addBan} disabled={!byName.has(banText.trim())}>
            Add ban
          </Button>
          {bans.map((id) => (
            <Button key={id} variant="ghost" className="line-through" onClick={() => setBans(bans.filter((b) => b !== id))} title="remove">
              {byId.get(id)?.name ?? id}
            </Button>
          ))}
        </div>
      </div>

      <Panel title="Evaluation">
        <ErrorText error={error} />
        {result ? (
          <div className="space-y-3">
            <div className="text-lg">
              <Mono>
                {result.total_points} / {result.point_cap}
              </Mono>{' '}
              <Badge tone={result.cap_status === 'EXACT' ? 'ok' : result.cap_status === 'OVER' ? 'bad' : 'warn'}>
                {result.cap_status}
                {result.cap_status === 'UNDER' ? ` (${result.unspent_points} unspent)` : ''}
              </Badge>
            </div>
            <Badge tone={result.is_legal ? 'ok' : 'bad'}>{result.is_legal ? 'legal' : 'illegal'}</Badge>
            <ul className="space-y-1 text-[12px]">
              {result.violations.map((v, i) => (
                <li key={i} className={clsx(v.severity === 'error' && 'text-bad', v.severity === 'warning' && 'text-warn', v.severity === 'info' && 'text-muted')}>
                  <Mono>{v.code}</Mono> {v.message}
                  {v.slot_nos.length ? <Mono className="text-muted"> [{v.slot_nos.join(',')}]</Mono> : null}
                </li>
              ))}
              {result.violations.length === 0 ? <li className="text-muted">no violations</li> : null}
            </ul>
            <details>
              <summary className="cursor-pointer text-muted">raw response</summary>
              <pre className="mono max-h-96 overflow-auto text-[11px]">{JSON.stringify(result, null, 2)}</pre>
            </details>
          </div>
        ) : (
          <Empty>Fill a slot to evaluate.</Empty>
        )}
      </Panel>
    </div>
  )
}
