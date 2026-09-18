import { useState } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import { useMe, useScrim } from '@/lib/api/hooks'
import type { SetDoc } from '@/lib/api/client'
import { Badge, Button, Empty, ErrorText, Mono, Panel, Select } from '@/components/ui'
import { useScrimStream } from './useScrimStream'
import { linkColor, readPosition, warpColor } from './shared'
import { useCompVocab } from '@/lib/api/hooks'

/** One slot, big: your ship, fit, warp-in and notes for the current round, with the EFT block ready to copy. */
export function PilotCardPage() {
  const { scrimId } = useParams({ from: '/scrims/$scrimId/me' })
  const id = Number(scrimId)
  const scrim = useScrim(id)
  const me = useMe()
  const stream = useScrimStream(id, Boolean(scrim.data))
  const vocab = useCompVocab()
  const remembered = readPosition(id) // the set and round left open on the scrim page
  const [setId, setSetId] = useState<number | null>(remembered?.setId ?? null)
  const [roundNo, setRoundNo] = useState<number | null>(remembered?.setId != null ? (remembered.roundBySet[remembered.setId] ?? null) : null)
  const [copied, setCopied] = useState(false)

  if (scrim.error) return <ErrorText error={scrim.error} />
  if (!scrim.data || !me.data) return <Empty>Loading…</Empty>
  const sets = scrim.data.sets
  const set: SetDoc | undefined = sets.find((s) => s.id === setId) ?? sets[sets.length - 1]
  const round = set?.rounds.find((r) => r.round_no === roundNo) ?? set?.rounds[set.rounds.length - 1]
  const mine = round?.us.slots.find((s) => s.pilot_user_id === me.data?.user_id)
  const copy = async () => {
    if (!mine?.fit_text) return
    try {
      await navigator.clipboard.writeText(mine.fit_text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      window.prompt('Copy the fit:', mine.fit_text)
    }
  }
  return (
    <div className="mx-auto max-w-2xl">
      <Panel
        title={
          <span>
            <Link to="/scrims/$scrimId" params={{ scrimId }} className="text-accent">
              {scrim.data.title}
            </Link>{' '}
            / my card <Badge tone={stream.status === 'live' ? 'ok' : 'muted'}>{stream.status}</Badge>
          </span>
        }
        testId="pilotcard"
        actions={
          <span className="flex items-center gap-1">
            {sets.length > 1 ? (
              <Select
                data-testid="pilotcard.set"
                className="h-6"
                value={set?.id ?? ''}
                onChange={(e) => {
                  setSetId(Number(e.target.value))
                  setRoundNo(null) // a new set opens on its latest round
                }}
              >
                {sets.map((s) => (
                  <option key={s.id} value={s.id}>
                    Set {s.index}
                    {s.comp_name ? ` · ${s.comp_name}` : ''}
                  </option>
                ))}
              </Select>
            ) : null}
            {set && set.rounds.length > 1 ? (
              <Select data-testid="pilotcard.round" className="h-6" value={round?.round_no ?? ''} onChange={(e) => setRoundNo(Number(e.target.value))}>
                {set.rounds.map((r) => (
                  <option key={r.round_no} value={r.round_no}>
                    R{r.round_no}
                  </option>
                ))}
              </Select>
            ) : null}
          </span>
        }
      >
        {!set || !round ? (
          <Empty>No sets yet.</Empty>
        ) : !mine ? (
          <Empty testId="pilotcard.empty">You are not in the lineup for set {set.index}, round {round.round_no}.</Empty>
        ) : (
          <div className="flex flex-col gap-3" data-testid="pilotcard.slot">
            <div className="flex flex-wrap items-end gap-4">
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted">ship</div>
                <div className="text-2xl font-semibold" data-testid="pilotcard.ship">
                  {mine.ship_name ?? '—'}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted">fit</div>
                <div className="text-lg" data-testid="pilotcard.fit">
                  {mine.fit_name ?? <span className="text-muted">none chosen</span>}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted">warp-in</div>
                <span className="mono inline-flex h-8 min-w-12 items-center justify-center rounded px-2 text-lg font-semibold text-[#0b1220]" style={{ backgroundColor: warpColor(mine.warp_in_km) ?? 'var(--panel-2)' }} data-testid="pilotcard.warp">
                  {mine.warp_in_km ?? '—'}
                </span>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-muted">round</div>
                <Mono className="text-lg">R{round.round_no}</Mono>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[12px]">
              <span className="text-muted">warp calls</span>
              {['1st', '2nd', '3rd', '4th'].map((label, i) => (
                <span key={label} className="rounded border border-line bg-bg px-1.5">
                  {label} <Mono className="text-fg">{set.warp_calls[i] || '—'}</Mono>
                </span>
              ))}
            </div>
            {mine.link_scripts.length ? (
              <div className="flex items-center gap-1 text-[12px]">
                <span className="text-muted">links</span>
                {mine.link_index ? <Badge tone="accent">L{mine.link_index}</Badge> : null}
                {mine.link_scripts.map((code) => (
                  <span key={code} className="mono rounded px-1.5 text-[#0b1220]" style={{ backgroundColor: linkColor(code, vocab.data?.link_scripts ?? []) }}>
                    {code}
                  </span>
                ))}
              </div>
            ) : null}
            {mine.repeat_note || mine.custom_note ? (
              <div className="rounded border border-line bg-bg p-2 text-[12px]">
                {mine.repeat_note ? <div className="text-muted">{mine.repeat_note}</div> : null}
                {mine.custom_note ? <div>{mine.custom_note}</div> : null}
              </div>
            ) : null}
            {set.tactics_note ? <div className="text-[12px]">tactics: {set.tactics_note}</div> : null}
            {mine.fit_text ? (
              <div>
                <Button variant="primary" onClick={copy} data-testid="pilotcard.copy">
                  {copied ? 'Copied' : 'Copy fit'}
                </Button>
                <pre className="mono mt-2 overflow-x-auto rounded border border-line bg-bg p-2 text-[12px] leading-snug">{mine.fit_text}</pre>
              </div>
            ) : (
              <p className="text-muted">No fit text on this slot yet.</p>
            )}
          </div>
        )}
      </Panel>
    </div>
  )
}
