import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useScrimHistory } from '@/lib/api/hooks'
import { Badge, Button, ErrorText, Mono } from '@/components/ui'
import type { Perms } from './shared'
import { whenAt } from './format'

const ACTION_LABELS: Record<string, string> = {
  'scrim.created': 'scrim created',
  'scrim.updated': 'scrim edited',
  'scrim.archived': 'scrim archived',
  'scrim.no_show_removed': 'removed as no-show',
  'scrim.attendance_set': 'attendance set',
  'set.created': 'set created',
  'set.deleted': 'set deleted',
  'set.restored': 'set restored',
  'round.deleted': 'round deleted',
  'round.restored': 'round restored',
  'share.created': 'share link created',
  'share.revoked': 'share link revoked',
}

/** Who did what on this scrim, newest first, plus the deleted sets and rounds a captain can bring back. */
export function HistoryDrawer({
  scrimId,
  perms,
  onClose,
  onRestoreSet,
  onRestoreRound,
  restoring,
  error,
}: {
  scrimId: number
  perms: Perms
  onClose: () => void
  onRestoreSet: (setId: number) => void
  onRestoreRound: (setId: number, roundNo: number) => void
  restoring: boolean
  error: unknown
}) {
  const history = useScrimHistory(scrimId)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const data = history.data
  return createPortal(
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onMouseDown={onClose} data-testid="scrim.history">
      <aside className="flex h-full w-[420px] flex-col gap-3 overflow-y-auto border-l border-line bg-panel p-3 text-[12px] shadow-lg" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-[12px] font-semibold uppercase tracking-wide text-muted">History</h2>
          <Button variant="ghost" className="h-6 px-1.5" onClick={onClose} data-testid="scrim.history.close">
            close
          </Button>
        </div>
        <ErrorText error={history.error ?? error} />
        {data && (data.deleted_sets.length || data.deleted_rounds.length) ? (
          <section className="rounded border border-warn/60 bg-warn/10 p-2">
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-warn">Deleted, can be restored</h3>
            <ul className="space-y-1">
              {data.deleted_sets.map((s) => (
                <li key={`s${s.id}`} className="flex items-center justify-between gap-2" data-testid={`scrim.history.deleted.set.${s.id}`}>
                  <span>
                    Set {s.index}
                    {s.comp_name ? ` · ${s.comp_name}` : ''} <span className="text-muted">({s.rounds} round{s.rounds === 1 ? '' : 's'}, by {s.deleted_by_name || 'unknown'} {whenAt(s.deleted_at)})</span>
                  </span>
                  {perms.manage ? (
                    <Button className="h-6 px-2" disabled={restoring} onClick={() => onRestoreSet(s.id)} data-testid={`scrim.history.deleted.set.${s.id}.restore`}>
                      Restore
                    </Button>
                  ) : null}
                </li>
              ))}
              {data.deleted_rounds.map((r) => (
                <li key={`r${r.set_id}-${r.round_no}`} className="flex items-center justify-between gap-2" data-testid={`scrim.history.deleted.round.${r.set_id}.${r.round_no}`}>
                  <span>
                    Set {r.set_index} R{r.round_no} <span className="text-muted">(by {r.deleted_by_name || 'unknown'} {whenAt(r.deleted_at)})</span>
                  </span>
                  {perms.manage ? (
                    <Button className="h-6 px-2" disabled={restoring || !r.restorable} title={r.restorable ? '' : 'a newer round exists; remove it first'} onClick={() => onRestoreRound(r.set_id, r.round_no)} data-testid={`scrim.history.deleted.round.${r.set_id}.${r.round_no}.restore`}>
                      Restore
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <ul className="space-y-1.5">
          {data?.entries.map((e) => (
            <li key={e.id} className="border-b border-line pb-1.5" data-testid={`scrim.history.entry.${e.id}`}>
              <div className="flex items-center justify-between gap-2">
                <span>
                  <b>{e.actor_name || 'system'}</b> {ACTION_LABELS[e.action] ?? e.action}
                  {e.target_label && !e.action.startsWith('scrim.') ? <span className="text-muted"> · {e.target_label}</span> : null}
                </span>
                <Mono className="text-[11px] text-muted">{whenAt(e.at)}</Mono>
              </div>
              {e.reason ? <div className="text-muted">"{e.reason}"</div> : null}
              {e.action === 'scrim.attendance_set' && e.after ? (
                <div className="text-muted">
                  {String(e.after.pilot)} <Badge>{String(e.after.attendance)}</Badge>
                </div>
              ) : null}
            </li>
          ))}
          {data && data.entries.length === 0 ? <li className="text-muted">Nothing recorded yet.</li> : null}
          {history.isLoading ? <li className="text-muted">Loading…</li> : null}
        </ul>
      </aside>
    </div>,
    document.body,
  )
}
