import clsx from 'clsx'
import type { SetDoc } from '@/lib/api/client'
import { MenuDots, useContextMenu, type MenuItem } from './ContextMenu'

/** R1 R2 R3 [+]: the same selection drives the results column, the lineups and the notes panel. */
export function RoundTabs({
  set,
  roundNo,
  onRound,
  onAdd,
  onDelete,
  testPrefix,
}: {
  set: SetDoc
  roundNo: number
  onRound: (n: number) => void
  onAdd?: () => void
  /** Managers only: delete a round. The server only accepts the last one, so earlier tabs show why. */
  onDelete?: (n: number) => void
  testPrefix: string
}) {
  const menu = useContextMenu()
  const last = set.rounds[set.rounds.length - 1]?.round_no
  const decided = set.rounds[set.rounds.length - 1]?.outcome !== 'none' // a new round only after the current one has a result
  const items = (n: number): MenuItem[] => [
    {
      label: `Delete R${n}`,
      danger: true,
      disabled: n !== last || n === 1,
      reason: n === 1 ? 'a set keeps its first round; delete the set instead' : n !== last ? 'later rounds copy from this one; delete the last round first' : undefined,
      onClick: () => {
        if (window.confirm(`Delete round ${n}? Its lineups and deaths go with it.`)) onDelete?.(n)
      },
    },
  ]
  return (
    <span className="flex items-center gap-0.5">
      {set.rounds.map((r) => (
        <span key={r.round_no} className="inline-flex items-center">
          <button
            type="button"
            data-testid={`${testPrefix}.round.${r.round_no}`}
            onClick={() => onRound(r.round_no)}
            onContextMenu={onDelete ? (e) => menu.open(e, items(r.round_no)) : undefined}
            className={clsx('rounded px-1.5 py-0.5 text-[12px]', r.round_no === roundNo ? 'bg-accent/15 font-medium text-accent' : 'text-muted hover:text-fg')}
          >
            R{r.round_no}
          </button>
        </span>
      ))}
      {menu.element}
      {onAdd ? (
        <button
          type="button"
          data-testid={`${testPrefix}.addround`}
          disabled={!decided}
          title={decided ? 'add a round (copies this lineup)' : `mark R${last}'s outcome before adding a round`}
          onClick={onAdd}
          className="rounded px-1.5 py-0.5 text-[12px] text-muted hover:text-fg disabled:cursor-default disabled:opacity-40 disabled:hover:text-muted"
        >
          +
        </button>
      ) : null}
      {onDelete ? <MenuDots always testId={`${testPrefix}.menu`} onClick={(e) => menu.open(e, items(roundNo))} /> : null}
    </span>
  )
}
