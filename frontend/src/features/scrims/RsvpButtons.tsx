import { useState } from 'react'
import clsx from 'clsx'
import { useScrimMutations } from '@/lib/api/hooks'
import type { SessionSummaryOut } from '@/lib/api/client'
import { Badge, Button, ErrorText, Input } from '@/components/ui'
import { RSVP_LABELS, rsvpTone } from './format'

/** Attending / Unable / Maybe for the viewer's own pilot. Maybe needs a reason, so it opens a field first. */
export function RsvpButtons({ scrim, testPrefix }: { scrim: Pick<SessionSummaryOut, 'id' | 'my_rsvp' | 'my_rsvp_reason'>; testPrefix: string }) {
  const { rsvp } = useScrimMutations()
  const [reason, setReason] = useState(scrim.my_rsvp_reason ?? '')
  const [askReason, setAskReason] = useState(false)

  if (scrim.my_rsvp === null) {
    return (
      <span className="text-[11px] text-muted" data-testid={`${testPrefix}.rsvp.none`}>
        not on the roster
      </span>
    )
  }

  const send = (value: string) => {
    if (value === 'maybe' && !reason.trim()) {
      setAskReason(true)
      return
    }
    rsvp.mutate({ id: scrim.id, rsvp: value, reason: value === 'maybe' ? reason : '' }, { onSuccess: () => setAskReason(false) })
  }
  const mark = (value: string, label: string) => (
    <Button
      data-testid={`${testPrefix}.rsvp.${value}`}
      variant={scrim.my_rsvp === value ? 'primary' : 'default'}
      disabled={rsvp.isPending}
      onClick={() => send(value)}
      className={clsx(scrim.my_rsvp === value && 'pointer-events-none')}
    >
      {label}
    </Button>
  )

  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={rsvpTone(scrim.my_rsvp)} testId={`${testPrefix}.rsvp.current`}>
        {RSVP_LABELS[scrim.my_rsvp] ?? scrim.my_rsvp}
      </Badge>
      {mark('yes', 'Attending')}
      {mark('no', 'Unable')}
      {askReason || scrim.my_rsvp === 'maybe' ? (
        <Input
          data-testid={`${testPrefix}.rsvp.reason`}
          className="w-44"
          placeholder="why maybe? (required)"
          invalid={askReason && !reason.trim()}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send('maybe')}
        />
      ) : null}
      {mark('maybe', 'Maybe')}
      {askReason && !reason.trim() ? (
        <span className="text-[11px] text-warn" data-testid={`${testPrefix}.rsvp.needs-reason`}>
          say why first
        </span>
      ) : null}
      <ErrorText error={rsvp.error} />
    </span>
  )
}
