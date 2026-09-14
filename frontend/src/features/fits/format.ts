import type { Tone } from '@/components/ui'

export const FIT_STATUSES = ['suggested', 'active', 'inactive', 'retired'] as const

export function statusTone(status: string): Tone {
  switch (status) {
    case 'active':
      return 'ok'
    case 'suggested':
      return 'info'
    case 'inactive':
      return 'warn'
    default:
      return 'muted'
  }
}

export function severityTone(severity: string): Tone {
  return severity === 'error' ? 'bad' : severity === 'warning' ? 'warn' : 'muted'
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return ''
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString() : ''
}
