import { useState } from 'react'
import clsx from 'clsx'
import type { RoundDoc, SlotDoc } from '@/lib/api/client'
import { Button, Panel } from '@/components/ui'
import type { Perms } from './shared'

export function FitsColumn({ round, perms }: { round: RoundDoc; perms: Perms }) {
  const mine = round.us.slots.filter((s) => perms.userId != null && s.pilot_user_id === perms.userId)
  const [mode, setMode] = useState<'mine' | 'all'>(mine.length ? 'mine' : 'all')
  const [copied, setCopied] = useState<number | null>(null)
  const shown = mode === 'mine' ? mine : round.us.slots.filter((s) => s.type_id != null)
  const copy = async (s: SlotDoc) => {
    try {
      await navigator.clipboard.writeText(s.fit_text)
      setCopied(s.slot_no)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      window.prompt('Copy the fit:', s.fit_text)
    }
  }
  return (
    <Panel
      title={`Fits · R${round.round_no}`}
      testId="scrim.fits"
      actions={
        <span className="flex gap-1">
          <Button data-testid="scrim.fits.mode.mine" className="h-6 px-2" variant={mode === 'mine' ? 'primary' : 'default'} onClick={() => setMode('mine')}>
            Mine
          </Button>
          <Button data-testid="scrim.fits.mode.all" className="h-6 px-2" variant={mode === 'all' ? 'primary' : 'default'} onClick={() => setMode('all')}>
            All
          </Button>
        </span>
      }
    >
      <div className="flex max-h-[80vh] flex-col gap-1.5 overflow-y-auto pr-0.5">
        {shown.length === 0 ? <p className="text-[12px] text-muted">{mode === 'mine' ? 'You are not in this round’s lineup.' : 'No ships assigned yet.'}</p> : null}
        {shown.map((s) => {
          const isMine = perms.userId != null && s.pilot_user_id === perms.userId
          return (
            <div key={s.slot_no} data-testid={`scrim.fits.card.${s.slot_no}`} className={clsx('flex min-w-0 flex-col gap-1 rounded border px-2 py-1.5 text-[12px]', isMine ? 'border-accent bg-accent/10' : 'border-line')}>
              <div className="flex items-center justify-between gap-1.5">
                <b className="truncate">
                  {s.slot_no} · {s.pilot_name ?? 'unassigned'} · {s.ship_name}
                </b>
                {s.fit_text ? (
                  <Button data-testid={`scrim.fits.card.${s.slot_no}.copy`} className="h-6 px-2" onClick={() => copy(s)}>
                    {copied === s.slot_no ? 'Copied' : 'Copy'}
                  </Button>
                ) : null}
              </div>
              <div className="text-muted">{s.fit_name ?? 'no fit chosen'}</div>
              {s.fit_text ? <pre className={clsx('mono m-0 overflow-hidden whitespace-pre text-[11px] leading-snug text-muted', mode === 'mine' ? '' : 'max-h-[62px]')}>{s.fit_text}</pre> : null}
            </div>
          )
        })}
      </div>
      <p className="mt-2 text-[11px] text-muted">Mine shows your slot with the whole EFT block; All lists every slot with a Copy button.</p>
    </Panel>
  )
}
