import clsx from 'clsx'
import type { SetDoc } from '@/lib/api/client'
import { Button, ErrorText, Panel } from '@/components/ui'
import type { Perms } from './shared'
import { outcomeLetter, outcomeTone } from './shared'
import { useContextMenu, type MenuItem } from './ContextMenu'

export function SetStepper({
  sets,
  selectedId,
  onSelect,
  perms,
  onCreate,
  onDelete,
  pending,
  error,
}: {
  sets: SetDoc[]
  selectedId: number | null
  onSelect: (id: number) => void
  perms: Perms
  onCreate: (copyPrevious: boolean) => void
  onDelete: (id: number, reason: string) => void
  pending: boolean
  error: unknown
}) {
  const menu = useContextMenu()
  const items = (s: SetDoc): MenuItem[] => [
    {
      label: 'Delete set',
      danger: true,
      onClick: () => {
        const reason = window.prompt(`Delete set ${s.index} and its ${s.rounds.length} round${s.rounds.length === 1 ? '' : 's'}? Reason (kept in the audit log):`)
        if (reason !== null) onDelete(s.id, reason)
      },
    },
  ]
  return (
    <Panel
      title="Sets"
      testId="scrim.sets"
      actions={
        perms.manage ? (
          <Button data-testid="scrim.sets.new" className="h-6 px-2" disabled={pending} onClick={() => onCreate(sets.length > 0)} title={sets.length ? 'copies the previous set (bans cleared)' : ''}>
            + New set
          </Button>
        ) : null
      }
    >
      <ErrorText error={error} />
      {sets.length === 0 ? <p className="text-[12px] text-muted">No sets yet.</p> : null}
      <div className="flex max-h-[40vh] flex-col gap-1.5 overflow-y-auto pr-0.5">
        {sets.map((s) => {
          const filled = (side: string) => s.bans.filter((b) => b.side === side && b.type_id != null).length
          const avalanche = s.avalanche_bans.filter((b) => b.type_id != null).length
          const ours = s.our_side
          const theirs = ours === 'A' ? 'B' : 'A'
          return (
            <div
              key={s.id}
              role="button"
              tabIndex={0}
              data-testid={`scrim.sets.card.${s.id}`}
              onClick={() => onSelect(s.id)}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(s.id)}
              onContextMenu={perms.manage ? (e) => menu.open(e, items(s)) : undefined}
              className={clsx('flex cursor-pointer flex-col gap-0.5 rounded border px-2 py-1.5 text-left text-[12px]', s.id === selectedId ? 'border-accent bg-accent/10' : 'border-line hover:border-muted')}
            >
              <span className="flex items-center justify-between gap-2 font-semibold">
                <span className="truncate">
                  Set {s.index}
                  {s.comp_name ? ` · ${s.comp_name}` : ''}
                </span>
                <span className="flex items-center gap-0.5">
                  {s.rounds.map((r) => (
                    <i
                      key={r.round_no}
                      title={`R${r.round_no}: ${r.outcome}`}
                      className={clsx(
                        'mono inline-flex h-4 w-4 items-center justify-center rounded-sm text-[10px] not-italic',
                        outcomeTone(r.outcome) === 'ok' && 'bg-ok/15 text-ok',
                        outcomeTone(r.outcome) === 'bad' && 'bg-bad/15 text-bad',
                        outcomeTone(r.outcome) === 'info' && 'bg-info/15 text-info',
                        outcomeTone(r.outcome) === 'muted' && 'bg-panel-2 text-muted',
                      )}
                    >
                      {outcomeLetter(r.outcome)}
                    </i>
                  ))}
                </span>
              </span>
              <span className="text-muted">
                {s.comp_name ? '' : 'no comp · '}
                bans {filled(ours)} · {filled(theirs)}
                {avalanche ? ` · avalanche ${avalanche}` : ''}
              </span>
            </div>
          )
        })}
      </div>
      {menu.element}
    </Panel>
  )
}
