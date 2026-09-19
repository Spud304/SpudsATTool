import { Badge, Mono } from '@/components/ui'
import type { EvaluateOut } from '@/lib/api/client'
import { severityTone } from '@/features/fits/format'

type Violation = EvaluateOut['violations'][number]

/** Slot flags worth colouring a row for: an empty slot is not a problem with the slot, only with the comp. */
export function rowFlags(flags: string[] | undefined): string[] {
  return (flags ?? []).filter((f) => f !== 'EMPTY_SLOT')
}

/** The evaluation's violations with the per-slot EMPTY_SLOT warnings folded into one line. */
export function ViolationList({ violations, slotCount, testId }: { violations: Violation[]; slotCount: number; testId?: string }) {
  const empty = violations.filter((v) => v.code === 'EMPTY_SLOT')
  const rest = violations.filter((v) => v.code !== 'EMPTY_SLOT')
  return (
    <ul className="space-y-1 text-[12px]" data-testid={testId}>
      {empty.length ? (
        <li className="text-muted" data-testid={testId ? `${testId}.empty` : undefined}>
          {empty.length} of {slotCount} slots empty
        </li>
      ) : null}
      {rest.map((v, i) => (
        <li key={i}>
          <Badge tone={severityTone(v.severity)}>{v.code}</Badge> {v.message}
          {v.slot_nos.length ? <Mono className="text-muted"> [{v.slot_nos.join(',')}]</Mono> : null}
        </li>
      ))}
      {violations.length === 0 ? <li className="text-muted">no violations</li> : null}
    </ul>
  )
}
