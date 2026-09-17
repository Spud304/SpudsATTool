import { useState } from 'react'
import clsx from 'clsx'
import type { BanChip, CompSummaryOut, SetDoc, ShipOut } from '@/lib/api/client'
import { Badge, Button, Mono, Panel, Select, Textarea } from '@/components/ui'
import { HullInput } from '@/features/comps/HullInput'
import type { Live, Perms } from './shared'
import { HULL_LIST_ID, remoteProps } from './shared'
import { useDebouncedField } from './useDebouncedField'
import { MenuDots, useContextMenu, type MenuItem } from './ContextMenu'

type Mutations = {
  patchSet: (body: Record<string, unknown>) => void
  putBan: (ban: { side: string; kind: string; index: number; type_id: number | null; in_effect_from_round?: number }) => void
  deleteSet: (reason: string) => void
}

export function BanBoard({
  set,
  stage,
  perms,
  live,
  byName,
  comps,
  compsLoading,
  m,
  className,
}: {
  className?: string
  set: SetDoc
  stage: string | null
  perms: Perms
  live: Live
  byName: Map<string, ShipOut>
  comps: CompSummaryOut[]
  compsLoading: boolean
  m: Mutations
}) {
  const [showTactics, setShowTactics] = useState(true) // open by default; collapse by hand when the board needs the room
  const menu = useContextMenu()
  const setMenu: MenuItem[] = [
    {
      label: 'Delete set',
      danger: true,
      onClick: () => {
        const reason = window.prompt(`Delete set ${set.index} and its ${set.rounds.length} round${set.rounds.length === 1 ? '' : 's'}? Reason (kept in the audit log):`)
        if (reason !== null) m.deleteSet(reason)
      },
    },
  ]
  const nextOrder = set.bans.find((b) => b.type_id == null)?.order ?? null
  const tactics = useDebouncedField(set.tactics_note, (v) => m.patchSet({ tactics_note: v }))
  const byRound = new Map<number, BanChip[]>()
  for (const b of set.avalanche_bans) byRound.set(b.in_effect_from_round, [...(byRound.get(b.in_effect_from_round) ?? []), b])
  const compOptions = set.comp_id != null && !comps.some((c) => c.id === set.comp_id) ? [{ id: set.comp_id, name: set.comp_name ?? `comp ${set.comp_id}`, banned: [] as string[] }, ...comps.map(summary)] : comps.map(summary)

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          Set {set.index} · bans
        </span>
      }
      testId="scrim.bans"
      className={className}
      actions={
        <span className="flex flex-wrap items-center justify-end gap-1.5">
          {perms.edit ? (
            <Select data-testid="scrim.bans.comp" className="h-6 max-w-[190px]" value={set.comp_id ?? ''} disabled={compsLoading} onChange={(e) => m.patchSet({ comp_id: e.target.value === '' ? null : Number(e.target.value) })} title="load a comp into our lineup">
              <option value="">no comp</option>
              {compOptions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.banned.length ? ` (${c.banned.length} banned)` : ''}
                </option>
              ))}
            </Select>
          ) : set.comp_name ? (
            <Mono className="text-fg">{set.comp_name}</Mono>
          ) : null}
          {perms.edit ? (
            <Button data-testid="scrim.bans.side" className="h-6 px-2" onClick={() => m.patchSet({ our_side: set.our_side === 'A' ? 'B' : 'A' })} title="which column counts against us">
              We are {set.our_side}
            </Button>
          ) : (
            <Badge tone="accent">Team {set.our_side}</Badge>
          )}
          <Badge>
            {stage ?? 'no stage'} · {set.bans_per_side} per side{set.bans_are_blind ? ' · blind' : ''}
          </Badge>
          {set.extra_bans_owed ? <Badge tone="warn">unique hull: +{set.extra_bans_owed} bans</Badge> : null}
          {perms.manage ? <MenuDots always testId="scrim.bans.menu" onClick={(e) => menu.open(e, setMenu)} /> : null}
          {menu.element}
        </span>
      }
    >
      {set.bans.length ? (
        <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${set.bans.length}, minmax(0, 1fr))` }}>
          {set.bans.map((b) => (
            <Chip key={`${b.side}-${b.index}`} chip={b} isNext={b.order === nextOrder} perms={perms} live={live} byName={byName} onPick={(type_id) => m.putBan({ side: b.side, kind: 'standard', index: b.index, type_id })} testId={`scrim.bans.chip.${b.order}`} />
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-muted">This scrim has no stage, so no ban phase. Set one in the header to get ban chips.</p>
      )}
      {[...byRound.entries()]
        .sort(([a], [b]) => a - b)
        .map(([fromRound, chips]) => (
          <div key={fromRound} className="mt-2 grid max-w-[60%] gap-1.5" style={{ gridTemplateColumns: `repeat(${chips.length + 1}, minmax(0, 1fr))` }}>
            <div className="flex items-center gap-2 px-2 text-[12px] text-muted">
              <Mono>R{fromRound - 1}</Mono> after round {fromRound - 1}
            </div>
            {chips.map((b) => (
              <Chip key={b.id ?? `${b.side}-${b.index}`} chip={b} avalanche isNext={false} perms={perms} live={live} byName={byName} onPick={(type_id) => m.putBan({ side: b.side, kind: b.kind, index: b.index, type_id, in_effect_from_round: b.in_effect_from_round })} testId={`scrim.bans.avalanche.${b.id}`} />
            ))}
          </div>
        ))}
      <div className="mt-2 flex items-start gap-2 border-t border-dashed border-line pt-1.5 text-[12px]">
        <button type="button" className="text-[11px] text-muted hover:text-fg" data-testid="scrim.bans.tactics.toggle" onClick={() => setShowTactics((v) => !v)}>
          {showTactics ? '▾' : '▸'} Tactics
        </button>
        {showTactics ? (
          perms.edit ? (
            <Textarea data-testid="scrim.bans.tactics" rows={2} className="w-full font-sans" placeholder="how we fly this set" value={tactics.value} onChange={(e) => tactics.onChange(e.target.value)} {...remoteProps(live, `set.${set.id}.tactics`)} onFocus={() => { tactics.onFocus(); live.setFocus(`set.${set.id}.tactics`) }} onBlur={() => { tactics.onBlur(); live.setFocus(null) }} />
          ) : (
            <span className="whitespace-pre-wrap" data-testid="scrim.bans.tactics">
              {set.tactics_note || <span className="text-muted">nothing written</span>}
            </span>
          )
        ) : set.tactics_note ? (
          <span className="truncate text-muted">{set.tactics_note}</span>
        ) : null}
      </div>
    </Panel>
  )
}

function summary(c: CompSummaryOut) {
  return { id: c.id, name: c.name, banned: c.evaluation?.banned_hulls ?? [] }
}

function Chip({
  chip,
  isNext,
  avalanche = false,
  perms,
  live,
  byName,
  onPick,
  testId,
}: {
  chip: BanChip
  isNext: boolean
  avalanche?: boolean
  perms: Perms
  live: Live
  byName: Map<string, ShipOut>
  onPick: (type_id: number | null) => void
  testId: string
}) {
  const field = `ban.${chip.side}.${chip.kind}.${chip.index}`
  const remote = remoteProps(live, field)
  return (
    <div
      data-testid={testId}
      title={`${chip.is_ours ? 'our' : 'their'} ban${chip.order ? ` #${chip.order}` : ''}${remote.title ? ` · ${remote.title}` : ''}`}
      style={remote.style}
      className={clsx(
        'flex min-w-0 items-center gap-2 rounded border px-2 py-1',
        chip.type_id == null && 'border-dashed',
        avalanche ? 'bg-[var(--ban-avalanche)]' : chip.side === 'A' ? 'bg-[var(--ban-a)]' : 'bg-[var(--ban-b)]', // side colours never move: Team A always bans first
        chip.is_ours ? 'border-accent' : 'border-line',
        isNext && 'outline outline-2 outline-offset-1 outline-accent',
      )}
    >
      <Mono className="min-w-[1.4em] text-muted">{chip.order ?? `${chip.side}${chip.index}`}</Mono>
      {perms.edit ? (
        <span onFocus={() => live.setFocus(field)} onBlur={() => live.setFocus(null)} className="min-w-0 flex-1">
          <HullInput listId={HULL_LIST_ID} className="h-6 w-full" testId={`${testId}.hull`} value={chip.ship_name ?? ''} lookup={byName} onPick={(s) => onPick(s?.type_id ?? null)} />
        </span>
      ) : (
        <span className={clsx('truncate text-[12px] font-medium', chip.type_id == null && 'text-muted')}>{chip.ship_name ?? (isNext ? 'next pick' : 'waiting')}</span>
      )}
    </div>
  )
}
