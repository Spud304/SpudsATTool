import type { Tone } from '@/components/ui'
import type { SessionSummaryOut } from '@/lib/api/client'

export const RSVP_LABELS: Record<string, string> = { yes: 'attending', no: 'unable', maybe: 'maybe', none: 'no answer' }
export const ATTENDANCE_OPTIONS = ['present', 'late', 'absent'] as const

export function rsvpTone(rsvp: string | null | undefined): Tone {
  switch (rsvp) {
    case 'yes':
      return 'ok'
    case 'maybe':
      return 'warn'
    case 'no':
      return 'bad'
    default:
      return 'muted'
  }
}

export function attendanceTone(attendance: string): Tone {
  switch (attendance) {
    case 'present':
      return 'ok'
    case 'late':
      return 'warn'
    case 'absent':
    case 'no_show':
      return 'bad'
    default:
      return 'muted'
  }
}

export function whenAt(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** ISO instant to the value a datetime-local input wants (local wall clock, minute precision). */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function fromLocalInput(value: string): string {
  return new Date(value).toISOString()
}

/** Set record for a night: wins-losses over every round played. */
export function record(sets: SessionSummaryOut['sets']): string {
  const outcomes = sets.flatMap((s) => s.outcomes)
  const wins = outcomes.filter((o) => o === 'win').length
  const losses = outcomes.filter((o) => o === 'loss').length
  return outcomes.some((o) => o === 'win' || o === 'loss' || o === 'draw') ? `${wins}-${losses}` : ''
}
