import type { Tone } from '@/components/ui'
import type { EvaluateOut, RulesetOut } from '@/lib/api/client'

export const COMP_STATUSES = ['suggested', 'construction', 'active', 'inactive', 'retired'] as const

export function compStatusTone(status: string): Tone {
  switch (status) {
    case 'active':
      return 'ok'
    case 'construction':
      return 'warn'
    case 'suggested':
      return 'info'
    default:
      return 'muted'
  }
}

export function capTone(capStatus: string | undefined): Tone {
  return capStatus === 'EXACT' ? 'ok' : capStatus === 'OVER' ? 'bad' : 'warn'
}

export type SizeCount = { size: string; label: string; count: number; max: number | null; over: boolean }

/** Per-size hull counts against the ruleset limits, from the evaluation's effective sizes. */
export function sizeCounts(ruleset: RulesetOut | undefined, evaluation: EvaluateOut | null | undefined): SizeCount[] {
  if (!ruleset) return []
  const counts = new Map<string, number>()
  for (const s of evaluation?.slots ?? []) {
    if (s.effective_hull_size) counts.set(s.effective_hull_size, (counts.get(s.effective_hull_size) ?? 0) + 1)
  }
  const overSizes = new Set(
    (evaluation?.violations ?? []).filter((v) => v.code === 'OVER_SIZE_LIMIT').map((v) => String(v.data.hull_size ?? v.data.size ?? '')),
  )
  return ruleset.hull_sizes.map((h) => ({
    size: h.size,
    label: h.label,
    count: counts.get(h.size) ?? 0,
    max: h.max_per_comp ?? null,
    over: overSizes.has(h.size) || (h.max_per_comp != null && (counts.get(h.size) ?? 0) > h.max_per_comp),
  }))
}
