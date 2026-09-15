import clsx from 'clsx'
import type { RoundDoc, SetDoc, SlotDoc } from '@/lib/api/client'
import { Button, Mono, Panel } from '@/components/ui'
import { RoundTabs } from './RoundTabs'
import type { Perms } from './shared'
import { diffClass, fmtDiff } from './shared'

type Mutations = {
  addRound: () => void
  deleteRound: (roundNo: number) => void
  patchRound: (roundNo: number, body: { outcome?: string | null; notes?: string | null }) => void
  toggleDied: (roundNo: number, side: 'US' | 'OPP', slot: SlotDoc) => void
}

const OUTCOMES: { value: string; label: string }[] = [
  { value: 'win', label: 'Win' },
  { value: 'loss', label: 'Loss' },
  { value: 'draw', label: 'Draw' },
  { value: 'reset', label: 'Reset' },
]

export function ResultsColumn({ set, round, onRound, perms, m }: { set: SetDoc; round: RoundDoc; onRound: (n: number) => void; perms: Perms; m: Mutations }) {
  const score = round.score
  const last = set.rounds[set.rounds.length - 1]
  return (
    <Panel
      title="Results"
      testId="scrim.results"
      actions={<RoundTabs set={set} roundNo={round.round_no} onRound={onRound} onAdd={perms.edit ? m.addRound : undefined} testPrefix="scrim.results" />}
    >
      <ShipList label="Ours" side="US" doc={round.us.slots} lost={round.us.points_lost} perms={perms} onToggle={(s) => m.toggleDied(round.round_no, 'US', s)} />
      <div className="my-2 flex flex-col gap-0.5 rounded border border-accent bg-accent/10 px-2 py-1.5 text-center" data-testid="scrim.results.score">
        <div className={clsx('text-[28px] font-semibold leading-none tabular-nums', diffClass(score.leader, score.indicator))} data-testid="scrim.results.diff">
          {fmtDiff(score.differential)}
        </div>
        <div className="mt-1 grid grid-cols-4 gap-0.5">
          {OUTCOMES.map((o) => (
            <Button
              key={o.value}
              data-testid={`scrim.results.outcome.${o.value}`}
              className="h-[22px] w-full justify-center gap-0 px-0 text-[11px]"
              variant={round.outcome === o.value ? 'primary' : o.value === 'reset' ? 'ghost' : 'default'}
              disabled={!perms.score}
              onClick={() => m.patchRound(round.round_no, { outcome: round.outcome === o.value ? 'none' : o.value })}
            >
              {o.label}
            </Button>
          ))}
        </div>
        <div className="text-[11px] text-muted" data-testid="scrim.results.record">
          {set.rounds.map((r) => (
            <span key={r.round_no}>
              R{r.round_no} <span className={diffClass(r.score.leader, 'none')}>{fmtDiff(r.score.differential)}</span>
              {' · '}
            </span>
          ))}
          set {set.record.wins}–{set.record.losses}
          {set.record.draws ? ` (${set.record.draws} draw)` : ''}
        </div>
        {perms.manage && set.rounds.length > 1 && round.round_no === last.round_no ? (
          <button type="button" className="text-[11px] text-muted hover:text-bad" data-testid="scrim.results.removeround" onClick={() => m.deleteRound(round.round_no)}>
            remove R{round.round_no}
          </button>
        ) : null}
      </div>
      <ShipList label="Theirs" side="OPP" doc={round.opp.slots} lost={round.opp.points_lost} perms={perms} onToggle={(s) => m.toggleDied(round.round_no, 'OPP', s)} />
      <p className="mt-1.5 text-[11px] leading-snug text-muted">{perms.score ? 'Click a ship to toggle its death.' : 'Scorers toggle deaths.'}</p>
    </Panel>
  )
}

function ShipList({ label, side, doc, lost, perms, onToggle }: { label: string; side: 'US' | 'OPP'; doc: SlotDoc[]; lost: number; perms: Perms; onToggle: (s: SlotDoc) => void }) {
  return (
    <div className="flex flex-col gap-[3px]">
      <div className="mb-0.5 flex justify-between text-[11px] font-semibold uppercase tracking-wide text-muted">
        <span>{label}</span>
        <Mono>lost {lost}</Mono>
      </div>
      {doc.map((s) => {
        const empty = s.type_id == null
        return (
          <button
            key={s.slot_no}
            type="button"
            data-testid={`scrim.results.${side === 'US' ? 'us' : 'opp'}.${s.slot_no}`}
            data-dead={s.died ? 'true' : 'false'}
            disabled={empty || !perms.score}
            onClick={() => onToggle(s)}
            title={s.pilot_name ?? s.opp_pilot_name ?? ''}
            className={clsx(
              'flex h-6 items-center justify-between gap-1.5 rounded border px-2 text-[12px] disabled:cursor-default',
              empty ? 'border-dashed border-line text-muted' : s.died ? 'border-bad bg-bad/10' : 'border-line bg-panel-2',
              !empty && perms.score && 'hover:border-muted',
            )}
          >
            <span className={clsx('truncate', s.died && 'text-bad line-through')}>{s.ship_name ?? 'empty'}</span>
            {!empty ? <Mono className={s.died ? 'text-bad' : 'text-muted'}>{s.total_points}</Mono> : null}
          </button>
        )
      })}
    </div>
  )
}
