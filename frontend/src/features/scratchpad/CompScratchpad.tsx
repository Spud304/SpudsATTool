import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { api, unwrap, type BanIn, type EvaluateOut, type ShipOut, type SlotIn } from '@/lib/api/client'

/** Utilitarian harness for the rules engine: pick a ruleset, fill slots, read the evaluation. */
export function CompScratchpad() {
  const rulesets = useQuery({
    queryKey: ['rulesets'],
    queryFn: async () => unwrap(await api.GET('/api/rulesets')),
  })
  const [code, setCode] = useState<string>('')
  useEffect(() => {
    if (!code && rulesets.data?.length) setCode(rulesets.data.find((r) => r.has_point_table)?.code ?? rulesets.data[0].code)
  }, [code, rulesets.data])
  const ruleset = rulesets.data?.find((r) => r.code === code)

  if (rulesets.isLoading) return <p className="text-muted">Loading rulesets…</p>
  if (rulesets.error) return <p className="text-bad">{String((rulesets.error as Error).message)} (endpoints are DEBUG-only until SSO lands)</p>
  if (!ruleset) return <p className="text-muted">No rulesets imported. Run import_ruleset.</p>

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <label className="text-muted">Ruleset</label>
        <select className="h-7 rounded border border-line bg-bg px-1" value={code} onChange={(e) => setCode(e.target.value)}>
          {rulesets.data!.map((r) => (
            <option key={r.code} value={r.code}>
              {r.code} {r.has_point_table ? '' : '(no point table)'}
            </option>
          ))}
        </select>
        <span className="mono text-muted">
          cap {ruleset.point_cap} · {ruleset.fielded_pilots} pilots · inflation {ruleset.inflation_enabled ? ruleset.inflation_mode : 'off'} · same hull max {ruleset.max_same_hull ?? '∞'}
        </span>
      </div>
      {ruleset.has_point_table ? <Editor key={ruleset.code} code={ruleset.code} fielded={ruleset.fielded_pilots} flagship={ruleset.flagship_enabled} /> : <p className="text-warn">This ruleset has no point table; nothing to evaluate.</p>}
    </div>
  )
}

type SlotState = { type_id: number | null; is_flagship: boolean; has_links: boolean }

function Editor({ code, fielded, flagship }: { code: string; fielded: number; flagship: boolean }) {
  const ships = useQuery({
    queryKey: ['rulesets', code, 'ships'],
    queryFn: async () => unwrap(await api.GET('/api/rulesets/{code}/ships', { params: { path: { code } } })),
    staleTime: Infinity,
  })
  const byName = useMemo(() => new Map((ships.data ?? []).map((s) => [s.name, s])), [ships.data])
  const byId = useMemo(() => new Map((ships.data ?? []).map((s) => [s.type_id, s])), [ships.data])

  const [slots, setSlots] = useState<SlotState[]>(() => Array.from({ length: fielded }, () => ({ type_id: null, is_flagship: false, has_links: false })))
  const [bans, setBans] = useState<number[]>([])
  const [banText, setBanText] = useState('')
  const [result, setResult] = useState<EvaluateOut | null>(null)
  const [error, setError] = useState<string | null>(null)

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
        setError((e as Error).message)
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
        <table className="w-full text-left text-[12px] [&_td]:border-t [&_td]:border-line [&_td]:px-2 [&_td]:py-1 [&_th]:px-2 [&_th]:py-1 [&_th]:text-muted">
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
                  <td className="mono text-muted">{i + 1}</td>
                  <td>
                    <HullInput value={ship?.name ?? ''} lookup={byName} onPick={(s) => update(i, { type_id: s?.type_id ?? null })} />
                  </td>
                  <td className="text-muted">{ship?.ship_class ?? ''}</td>
                  <td className="mono">{ev?.effective_hull_size ?? ship?.hull_size ?? ''}</td>
                  {flagship ? (
                    <td>
                      <input type="checkbox" checked={slot.is_flagship} onChange={(e) => update(i, { is_flagship: e.target.checked })} />
                    </td>
                  ) : null}
                  <td>
                    <input type="checkbox" checked={slot.has_links} onChange={(e) => update(i, { has_links: e.target.checked })} />
                    {ev?.link_index ? <span className="mono ml-1 text-muted">L{ev.link_index}</span> : null}
                  </td>
                  <td className="mono text-right">
                    {ev && ev.type_id != null ? (
                      <>
                        {ev.total_points}
                        {ev.inflation_points ? <span className="text-warn"> ({ev.base_points}+{ev.inflation_points})</span> : null}
                      </>
                    ) : (
                      ''
                    )}
                  </td>
                  <td className="mono text-bad">{ev?.flags.join(' ')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-muted">Bans</span>
          <input
            list="hulls"
            className="h-7 rounded border border-line bg-bg px-2 text-[12px]"
            placeholder="hull name"
            value={banText}
            onChange={(e) => setBanText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addBan()}
          />
          <button className="h-7 rounded border border-line bg-panel-2 px-2 text-[12px]" onClick={addBan} disabled={!byName.has(banText.trim())}>
            Add ban
          </button>
          {bans.map((id) => (
            <button key={id} className="rounded border border-line bg-panel-2 px-2 py-0.5 text-[12px] line-through" onClick={() => setBans(bans.filter((b) => b !== id))} title="remove">
              {byId.get(id)?.name ?? id}
            </button>
          ))}
        </div>
      </div>

      <aside className="space-y-3 rounded border border-line bg-panel p-3">
        {error ? <p className="text-bad">{error}</p> : null}
        {result ? (
          <>
            <div className="mono text-lg">
              {result.total_points} / {result.point_cap}{' '}
              <span className={clsx('text-[12px]', result.cap_status === 'EXACT' && 'text-ok', result.cap_status === 'OVER' && 'text-bad', result.cap_status === 'UNDER' && 'text-warn')}>
                {result.cap_status}
                {result.cap_status === 'UNDER' ? ` (${result.unspent_points} unspent)` : ''}
              </span>
            </div>
            <div className={clsx('font-semibold', result.is_legal ? 'text-ok' : 'text-bad')}>{result.is_legal ? 'LEGAL' : 'ILLEGAL'}</div>
            <ul className="space-y-1 text-[12px]">
              {result.violations.map((v, i) => (
                <li key={i} className={clsx(v.severity === 'error' && 'text-bad', v.severity === 'warning' && 'text-warn', v.severity === 'info' && 'text-muted')}>
                  <span className="mono">{v.code}</span> {v.message}
                  {v.slot_nos.length ? <span className="mono text-muted"> [{v.slot_nos.join(',')}]</span> : null}
                </li>
              ))}
              {result.violations.length === 0 ? <li className="text-muted">no violations</li> : null}
            </ul>
            <details>
              <summary className="cursor-pointer text-muted">raw response</summary>
              <pre className="mono max-h-96 overflow-auto text-[11px]">{JSON.stringify(result, null, 2)}</pre>
            </details>
          </>
        ) : (
          <p className="text-muted">Fill a slot to evaluate.</p>
        )}
      </aside>
    </div>
  )
}

function HullInput({ value, lookup, onPick }: { value: string; lookup: Map<string, ShipOut>; onPick: (s: ShipOut | null) => void }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  const commit = () => {
    const t = text.trim()
    if (t === '') return onPick(null)
    const s = lookup.get(t)
    if (s) onPick(s)
    else setText(value)
  }
  return (
    <input
      list="hulls"
      className={clsx('h-7 w-56 rounded border border-line bg-bg px-2 text-[12px]', text && !lookup.has(text.trim()) && 'border-warn')}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && commit()}
      placeholder="hull"
    />
  )
}
