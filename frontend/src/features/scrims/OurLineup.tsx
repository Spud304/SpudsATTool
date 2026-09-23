import clsx from 'clsx'
import type { AttendanceOut, FitSummaryOut, LinkScriptOut, PilotOut, RoundDoc, SetDoc, ShipOut, SlotDoc } from '@/lib/api/client'
import { useEffect, useRef, useState } from 'react'
import { Badge, Checkbox, Input, Mono, Panel, Select, Table } from '@/components/ui'
import { HullInput } from '@/features/comps/HullInput'
import type { Live, Perms } from './shared'
import { HULL_LIST_ID, NO_SPINNER, focusShipRow, linkColor, remoteProps, warpColor } from './shared'
import { NoteCell } from './NoteCell'
import { usePilotHistory } from '@/lib/api/hooks'

type Mutations = {
  patchSet: (body: Record<string, unknown>) => void
  patchSlot: (roundNo: number, side: 'US', slotNo: number, body: Record<string, unknown>) => void
}

export type PilotOption = { id: number; name: string; group: 'attending' | 'maybe' | 'other' }

export function pilotOptions(attendance: AttendanceOut[], pilots: PilotOut[]): PilotOption[] {
  const seen = new Set<number>()
  const out: PilotOption[] = []
  for (const a of attendance) {
    if (a.rsvp === 'yes' || a.attendance === 'present' || a.attendance === 'late') {
      out.push({ id: a.pilot_id, name: a.pilot_name, group: 'attending' })
      seen.add(a.pilot_id)
    }
  }
  for (const a of attendance) {
    if (a.rsvp === 'maybe' && !seen.has(a.pilot_id)) {
      out.push({ id: a.pilot_id, name: a.pilot_name, group: 'maybe' })
      seen.add(a.pilot_id)
    }
  }
  for (const p of pilots) if (!seen.has(p.id)) out.push({ id: p.id, name: p.name, group: 'other' })
  return out
}

export function OurLineup({
  set,
  round,
  perms,
  live,
  byName,
  fitsByShip,
  pilots,
  warpLabels,
  linkScripts,
  m,
  scrimId,
}: {
  scrimId: number
  set: SetDoc
  round: RoundDoc
  perms: Perms
  live: Live
  byName: Map<string, ShipOut>
  fitsByShip: Map<number, FitSummaryOut[]>
  pilots: PilotOption[]
  warpLabels: string[]
  linkScripts: LinkScriptOut[]
  m: Mutations
}) {
  const us = round.us
  const linkCount = us.slots.filter((s) => s.has_links).length
  const calls = [0, 1, 2, 3].map((i) => set.warp_calls[i] ?? '')
  const setCall = (i: number, value: string) => {
    const next = [...calls]
    next[i] = value
    while (next.length && next[next.length - 1] === '') next.pop()
    m.patchSet({ warp_calls: next })
  }
  return (
    <Panel
      title={
        <span className="flex items-center gap-2.5">
          Ours · R{round.round_no}
          <Badge tone={us.is_legal ? 'ok' : 'bad'} testId="scrim.ours.legal">
            {us.is_legal ? 'legal' : `${us.violations.filter((v) => v.severity === 'error').length} err`}
          </Badge>
          <Mono className="text-fg" testId="scrim.ours.points">
            {us.total_points} / {us.point_cap}
          </Mono>
          {us.cap_status === 'OVER' ? <Badge tone="bad">over by {us.total_points - us.point_cap}</Badge> : us.unspent_points ? <Badge tone="warn">{us.unspent_points} unspent</Badge> : null}
          {linkCount ? <Badge tone="accent">links {linkCount}</Badge> : null}
        </span>
      }
      testId="scrim.ours"
      actions={
        <span className="flex items-center gap-1">
          {['1st', '2nd', '3rd', '4th'].map((label, i) =>
            perms.edit ? (
              <Select key={label} data-testid={`scrim.ours.warp.${i + 1}`} className="h-6 w-[88px]" value={calls[i]} onChange={(e) => setCall(i, e.target.value)} title={`${label} warp call`}>
                <option value="">{label}</option>
                {warpLabels.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </Select>
            ) : (
              <span key={label} className="rounded border border-line bg-bg px-1.5 text-[11px]">
                {label} <Mono className="text-fg">{calls[i] || '—'}</Mono>
              </span>
            ),
          )}
        </span>
      }
    >
      <Table>
        <thead>
          <tr>
            <th>#</th>
            <th>Pilot</th>
            <th>Ship</th>
            <th>Fit</th>
            <th>Warp</th>
            <th>Links</th>
            <th>Comp note</th>
            <th>Note</th>
            <th className="text-right">Pts</th>
          </tr>
        </thead>
        <tbody>
          {us.slots.map((s) => (
            <OurRow key={s.slot_no} slot={s} scrimId={scrimId} set={set} round={round} perms={perms} live={live} byName={byName} fits={s.type_id != null ? fitsByShip.get(s.type_id) ?? [] : []} pilots={pilots} linkScripts={linkScripts} patch={(body) => m.patchSlot(round.round_no, 'US', s.slot_no, body)} />
          ))}
        </tbody>
      </Table>
      {us.violations.filter((v) => v.severity === 'error').length ? (
        <ul className="mt-1 text-[11px] text-bad" data-testid="scrim.ours.violations">
          {us.violations
            .filter((v) => v.severity === 'error')
            .map((v, i) => (
              <li key={i}>{v.message}</li>
            ))}
        </ul>
      ) : null}
    </Panel>
  )
}

function OurRow({
  slot: s,
  set,
  perms,
  live,
  byName,
  fits,
  pilots,
  linkScripts,
  patch,
  scrimId,
}: {
  scrimId: number
  slot: SlotDoc
  set: SetDoc
  round: RoundDoc
  perms: Perms
  live: Live
  byName: Map<string, ShipOut>
  fits: FitSummaryOut[]
  pilots: PilotOption[]
  linkScripts: LinkScriptOut[]
  patch: (body: Record<string, unknown>) => void
}) {
  const id = `scrim.ours.row.${s.slot_no}`
  const mine = perms.userId != null && s.pilot_user_id === perms.userId
  const own = !perms.locked && (perms.edit || mine) // pilots may change fit, warp and note on their own slot
  const field = (name: string) => `set.${set.id}.us.${s.slot_no}.${name}`
  const duplicate = s.flags.includes('DUPLICATE_PILOT')
  const groups: PilotOption['group'][] = ['attending', 'maybe', 'other']
  const history = usePilotHistory(s.type_id, scrimId, perms.edit)
  const flew = history.data ?? []
  const fitOptions = s.fit_id != null && !fits.some((f) => f.id === s.fit_id) ? [{ id: s.fit_id, name: s.fit_name ?? `fit ${s.fit_id}`, status: 'unknown', has_links: s.has_links } as FitSummaryOut, ...fits] : fits
  return (
    <tr data-testid={id} className={clsx(mine && 'outline outline-2 -outline-offset-2 outline-accent', (s.is_banned || duplicate) && 'bg-bad/25')}>
      <td>
        <Mono className="text-muted">{s.slot_no}</Mono>
      </td>
      <td className="whitespace-nowrap">
        {perms.edit ? (
          <Select data-testid={`${id}.pilot`} className="h-6 max-w-[150px]" value={s.pilot_id ?? ''} onChange={(e) => patch({ pilot_id: e.target.value === '' ? null : Number(e.target.value) })} {...remoteProps(live, field('pilot'))} onFocus={() => live.setFocus(field('pilot'))} onBlur={() => live.setFocus(null)}>
            <option value="">{'—'}</option>
            {s.pilot_id != null && !pilots.some((p) => p.id === s.pilot_id) ? <option value={s.pilot_id}>{s.pilot_name}</option> : null}
            {flew.length ? (
              <optgroup label="flew this hull">
                {flew.map((h) => (
                  <option key={`h${h.pilot_id}`} value={h.pilot_id}>
                    {h.pilot_name} ({h.flights})
                  </option>
                ))}
              </optgroup>
            ) : null}
            {groups.map((g) => {
              const opts = pilots.filter((p) => p.group === g)
              return opts.length ? (
                <optgroup key={g} label={g}>
                  {opts.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </optgroup>
              ) : null
            })}
          </Select>
        ) : (
          <span className={clsx(!s.pilot_name && 'text-muted')}>
            {s.pilot_name ?? '—'}
            {mine ? <Badge tone="accent">you</Badge> : null}
          </span>
        )}
        {duplicate ? (
          <Badge tone="bad" testId={`${id}.duplicate`}>
            twice
          </Badge>
        ) : null}
      </td>
      <td>
        <span className="flex items-center gap-1">
          {perms.edit ? (
            <span onFocus={() => live.setFocus(field('ship'))} onBlur={() => live.setFocus(null)} style={remoteProps(live, field('ship')).style} title={remoteProps(live, field('ship')).title}>
              <HullInput
                listId={HULL_LIST_ID}
                className="h-6 w-36"
                testId={`${id}.ship`}
                value={s.ship_name ?? ''}
                lookup={byName}
                onPick={(ship) => patch({ type_id: ship?.type_id ?? null })}
                onEnter={() => focusShipRow('ours', s.slot_no + 1)}
                onArrow={(d) => focusShipRow('ours', s.slot_no + d)}
              />
            </span>
          ) : (
            <span className={clsx(s.died && 'text-bad line-through', !s.ship_name && 'text-muted')} data-testid={`${id}.ship`}>
              {s.ship_name ?? 'empty'}
            </span>
          )}
          {s.is_flagship ? <Badge tone="info">flag</Badge> : null}
          {s.is_banned ? <Badge tone="bad">banned</Badge> : null}
          {perms.edit ? (
            <>
              <label className="flex items-center gap-0.5 text-[10px] text-muted" title="flagship">
                <Checkbox data-testid={`${id}.flag`} checked={s.is_flagship} onChange={(e) => patch({ is_flagship: e.target.checked })} />F
              </label>
              {set.comp_id != null ? (
                <label className="flex items-center gap-0.5 text-[10px] text-muted" title="load the comp's defaults for this slot">
                  <Checkbox data-testid={`${id}.default`} checked={s.load_default} onChange={(e) => patch({ load_default: e.target.checked })} />D
                </label>
              ) : null}
            </>
          ) : null}
        </span>
      </td>
      <td>
        {own && s.type_id != null ? (
          <Select data-testid={`${id}.fit`} className="h-6 max-w-[170px]" value={s.fit_id ?? ''} onChange={(e) => patch({ fit_id: e.target.value === '' ? null : Number(e.target.value) })} {...remoteProps(live, field('fit'))} onFocus={() => live.setFocus(field('fit'))} onBlur={() => live.setFocus(null)}>
            <option value="">{fitOptions.length ? 'no fit' : 'no fits for hull'}</option>
            {fitOptions.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
                {f.has_links ? ' ⟟' : ''}
              </option>
            ))}
          </Select>
        ) : (
          <span className={clsx(!s.fit_name && 'text-muted')} data-testid={`${id}.fit`}>
            {s.fit_name ?? '—'}
          </span>
        )}
      </td>
      <td>
        {own ? (
          <WarpInput testId={`${id}.warp`} server={s.warp_in_km} live={live} field={field('warp')} onSave={(v) => patch({ warp_in_km: v })} />
        ) : (
          <Mono className="inline-block min-w-8 rounded px-1.5 text-center font-semibold" testId={`${id}.warp`}>
            <span className="text-[#0b1220]" style={{ backgroundColor: warpColor(s.warp_in_km), display: 'block', borderRadius: 4 }}>{s.warp_in_km ?? ''}</span>
          </Mono>
        )}
      </td>
      <td>
        <span className="flex items-center gap-1 whitespace-nowrap">
          {s.link_index ? <Badge tone="accent">L{s.link_index}</Badge> : null}
          {perms.edit && (s.has_links || s.link_scripts.length) ? (
            Array.from({ length: Math.min(5, s.link_scripts.length + 1) }, (_, k) => (
              <Select
                key={k}
                data-testid={`${id}.script.${k + 1}`}
                className="h-6 w-14 px-0.5 text-[#0b1220]"
                style={{ backgroundColor: linkColor(s.link_scripts[k] ?? '', linkScripts) }}
                value={s.link_scripts[k] ?? ''}
                onChange={(e) => {
                  const next = [...s.link_scripts]
                  if (e.target.value === '') next.splice(k, 1)
                  else next[k] = e.target.value
                  patch({ link_scripts: next.filter(Boolean) })
                }}
              >
                <option value="">{'—'}</option>
                {linkScripts.map((l) => (
                  <option key={l.code} value={l.code} disabled={s.link_scripts.includes(l.code) && s.link_scripts[k] !== l.code}>
                    {l.code}
                  </option>
                ))}
              </Select>
            ))
          ) : (
            s.link_scripts.map((code) => (
              <span key={code} className="mono rounded px-1 text-[#0b1220]" style={{ backgroundColor: linkColor(code, linkScripts) }}>
                {code}
              </span>
            ))
          )}
        </span>
      </td>
      <td>
        <NoteCell value={s.repeat_note} readOnly width="w-40" testId={`${id}.repeat`} />
      </td>
      <td>
        {own ? (
          <NoteCell value={s.custom_note} onSave={(v) => patch({ custom_note: v })} width="w-44" testId={`${id}.note`} live={live} field={field('note')} />
        ) : (
          <NoteCell value={s.custom_note} readOnly width="w-44" testId={`${id}.note`} />
        )}
      </td>
      <td className="text-right" data-testid={`${id}.pts`}>
        {s.type_id != null ? (
          <Mono>
            {s.total_points}
            {s.inflation_points ? <span className="text-warn"> +{s.inflation_points}</span> : null}
          </Mono>
        ) : null}
      </td>
    </tr>
  )
}


/** Warp-in km: a local draft saved on blur or Enter, so typing "25" is one save of 25, not 2 then 5. */
function WarpInput({ testId, server, live, field, onSave }: { testId: string; server: number | null; live: Live; field: string; onSave: (v: number | null) => void }) {
  const [text, setText] = useState(server == null ? '' : String(server))
  const focused = useRef(false)
  useEffect(() => {
    if (!focused.current) setText(server == null ? '' : String(server))
  }, [server])
  const commit = () => {
    const next = text.trim() === '' ? null : Math.round(Number(text))
    if (next != null && (!Number.isFinite(next) || next < 0 || next > 1000)) {
      setText(server == null ? '' : String(server))
      return
    }
    if (next !== server) onSave(next)
  }
  const parsed = Number(text)
  const shown = text.trim() === '' || !Number.isFinite(parsed) ? null : parsed
  const remote = remoteProps(live, field)
  return (
    <Input
      data-testid={testId}
      type="number"
      className={clsx('mono h-6 w-12 text-center font-semibold', NO_SPINNER)}
      min={0}
      max={1000}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
      }}
      {...remote}
      style={{ backgroundColor: warpColor(shown), borderColor: warpColor(shown), color: shown != null ? '#0b1220' : undefined, ...remote.style }}
      onFocus={() => {
        focused.current = true
        live.setFocus(field)
      }}
      onBlur={() => {
        focused.current = false
        live.setFocus(null)
        commit()
      }}
    />
  )
}
