import type { RoundDoc, SetDoc } from '@/lib/api/client'
import { Panel } from '@/components/ui'
import { RoundTabs } from './RoundTabs'
import type { Live, Perms } from './shared'
import { remoteProps } from './shared'
import { useDebouncedField } from './useDebouncedField'

/** One note per round, next to their lineup; the tabs are the same selection as the results column. */
export function RoundNotes({
  set,
  round,
  onRound,
  onAdd,
  perms,
  live,
  save,
}: {
  set: SetDoc
  round: RoundDoc
  onRound: (n: number) => void
  onAdd?: () => void
  perms: Perms
  live: Live
  save: (roundNo: number, notes: string) => void
}) {
  const note = useDebouncedField(round.notes, (v) => save(round.round_no, v))
  const field = `round.${round.id}.notes`
  return (
    <Panel title={`Notes · R${round.round_no}`} testId="scrim.notes" actions={<RoundTabs set={set} roundNo={round.round_no} onRound={onRound} onAdd={onAdd} testPrefix="scrim.notes" />}>
      {perms.score ? (
        <textarea
          key={round.id}
          data-testid="scrim.notes.text"
          rows={8}
          placeholder="what happened this round"
          style={{ fontFamily: 'var(--font-sans)', ...remoteProps(live, field).style }}
          title={remoteProps(live, field).title}
          className="w-full resize-y rounded border border-line bg-bg p-2 text-[12px] leading-snug text-fg placeholder:text-muted focus:border-accent focus:outline-none"
          value={note.value}
          onChange={(e) => note.onChange(e.target.value)}
          onFocus={() => {
            note.onFocus()
            live.setFocus(field)
          }}
          onBlur={() => {
            note.onBlur()
            live.setFocus(null)
          }}
        />
      ) : (
        <p className="min-h-[60px] whitespace-pre-wrap text-[12px]" data-testid="scrim.notes.text">
          {round.notes || <span className="text-muted">nothing written for this round</span>}
        </p>
      )}
    </Panel>
  )
}
