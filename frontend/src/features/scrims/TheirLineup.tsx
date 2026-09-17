import { useState } from 'react'
import clsx from 'clsx'
import type { ArchetypeOut, RoundDoc, SetDoc, ShipOut, SlotDoc } from '@/lib/api/client'
import { Badge, Button, Checkbox, ErrorText, Mono, Panel, Select, Table, Textarea } from '@/components/ui'
import { HullInput } from '@/features/comps/HullInput'
import type { Live, Perms } from './shared'
import { HULL_LIST_ID, focusShipRow, remoteProps } from './shared'
import { NoteCell } from './NoteCell'

type Mutations = {
  patchSet: (body: Record<string, unknown>) => void
  patchSlot: (roundNo: number, side: 'OPP', slotNo: number, body: Record<string, unknown>) => void
  pasteOpp: (roundNo: number, text: string) => Promise<{ unresolved: string[] }>
}

export function TheirLineup({ set, round, perms, live, byName, archetypes, m }: { set: SetDoc; round: RoundDoc; perms: Perms; live: Live; byName: Map<string, ShipOut>; archetypes: ArchetypeOut[]; m: Mutations }) {
  const opp = round.opp
  const [pasting, setPasting] = useState(false)
  const [text, setText] = useState('')
  const [unresolved, setUnresolved] = useState<string[]>([])
  const [error, setError] = useState<unknown>(null)
  return (
    <Panel
      title={
        <span className="flex items-center gap-2.5">
          Theirs · R{round.round_no}
          {perms.edit ? (
            <Select data-testid="scrim.theirs.archetype" className="h-6 w-32 font-normal normal-case tracking-normal" value={set.opp_archetype_id ?? ''} onChange={(e) => m.patchSet({ opp_archetype_id: e.target.value === '' ? null : Number(e.target.value) })}>
              <option value="">archetype?</option>
              {archetypes
                .filter((a) => !a.is_retired || a.id === set.opp_archetype_id)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </Select>
          ) : set.opp_archetype_id != null ? (
            <Badge>{archetypes.find((a) => a.id === set.opp_archetype_id)?.name ?? 'archetype'}</Badge>
          ) : null}
          <Mono className="text-fg" testId="scrim.theirs.points">
            {opp.total_points} / {opp.point_cap}
          </Mono>
          {opp.cap_status === 'OVER' ? <Badge tone="bad">over by {opp.total_points - opp.point_cap}</Badge> : opp.unspent_points ? <Badge tone="warn">{opp.unspent_points} unspent</Badge> : null}
        </span>
      }
      testId="scrim.theirs"
      actions={
        perms.edit ? (
          <Button variant="ghost" className="h-6 px-1.5" data-testid="scrim.theirs.paste" onClick={() => setPasting((v) => !v)}>
            {pasting ? 'close' : 'Paste lineup'}
          </Button>
        ) : null
      }
    >
      {pasting ? (
        <div className="mb-2 flex items-start gap-2">
          <Textarea data-testid="scrim.theirs.paste.text" rows={3} className="w-72" placeholder={'one hull per line (or comma separated)\nVindicator\nAstarte'} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex flex-col gap-1">
            <Button
              data-testid="scrim.theirs.paste.apply"
              variant="primary"
              className="h-6"
              disabled={!text.trim()}
              onClick={async () => {
                setError(null)
                try {
                  const out = await m.pasteOpp(round.round_no, text)
                  setUnresolved(out.unresolved)
                  if (!out.unresolved.length) {
                    setText('')
                    setPasting(false)
                  }
                } catch (e) {
                  setError(e)
                }
              }}
            >
              Apply
            </Button>
            {unresolved.length ? (
              <span className="text-[11px] text-warn" data-testid="scrim.theirs.paste.unresolved">
                not hulls in this ruleset: {unresolved.join(', ')}
              </span>
            ) : null}
            <ErrorText error={error} />
          </div>
        </div>
      ) : null}
      <Table>
        <thead>
          <tr>
            <th>#</th>
            <th>Ship</th>
            <th className="w-8">Flag</th>
            <th>Note</th>
            <th className="w-14 text-right">Pts</th>
          </tr>
        </thead>
        <tbody>
          {opp.slots.map((s) => (
            <TheirRow key={s.slot_no} slot={s} setId={set.id} perms={perms} live={live} byName={byName} patch={(body) => m.patchSlot(round.round_no, 'OPP', s.slot_no, body)} />
          ))}
        </tbody>
      </Table>
    </Panel>
  )
}

function TheirRow({ slot: s, setId, perms, live, byName, patch }: { slot: SlotDoc; setId: number; perms: Perms; live: Live; byName: Map<string, ShipOut>; patch: (body: Record<string, unknown>) => void }) {
  const id = `scrim.theirs.row.${s.slot_no}`
  const field = (name: string) => `set.${setId}.opp.${s.slot_no}.${name}`
  return (
    <tr data-testid={id} className={clsx(s.is_banned && 'bg-bad/25')}>
      <td>
        <Mono className="text-muted">{s.slot_no}</Mono>
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
                onEnter={() => focusShipRow('theirs', s.slot_no + 1)}
                onArrow={(d) => focusShipRow('theirs', s.slot_no + d)}
              />
            </span>
          ) : (
            <span className={clsx(s.died && 'text-bad line-through', !s.ship_name && 'text-muted')} data-testid={`${id}.ship`}>
              {s.ship_name ?? 'empty'}
            </span>
          )}
          {s.is_banned ? <Badge tone="bad">banned</Badge> : null}
        </span>
      </td>
      <td>
        <Checkbox data-testid={`${id}.flag`} checked={s.is_flagship} disabled={!perms.edit} onChange={(e) => patch({ is_flagship: e.target.checked })} />
      </td>
      <td>
        {perms.edit ? (
          <NoteCell value={s.custom_note} onSave={(v) => patch({ custom_note: v })} width="w-40" testId={`${id}.note`} live={live} field={field('note')} />
        ) : (
          <NoteCell value={s.custom_note} readOnly width="w-40" testId={`${id}.note`} />
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
