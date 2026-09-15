import clsx from 'clsx'
import type { SetDoc } from '@/lib/api/client'

/** R1 R2 R3 [+]: the same selection drives the results column, the lineups and the notes panel. */
export function RoundTabs({ set, roundNo, onRound, onAdd, testPrefix }: { set: SetDoc; roundNo: number; onRound: (n: number) => void; onAdd?: () => void; testPrefix: string }) {
  return (
    <span className="flex items-center gap-0.5">
      {set.rounds.map((r) => (
        <button
          key={r.round_no}
          type="button"
          data-testid={`${testPrefix}.round.${r.round_no}`}
          onClick={() => onRound(r.round_no)}
          className={clsx('rounded px-1.5 py-0.5 text-[12px]', r.round_no === roundNo ? 'bg-accent/15 font-medium text-accent' : 'text-muted hover:text-fg')}
        >
          R{r.round_no}
        </button>
      ))}
      {onAdd ? (
        <button type="button" data-testid={`${testPrefix}.addround`} title="add a round (copies this lineup)" onClick={onAdd} className="rounded px-1.5 py-0.5 text-[12px] text-muted hover:text-fg">
          +
        </button>
      ) : null}
    </span>
  )
}
