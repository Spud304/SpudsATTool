import { useEffect, useState } from 'react'
import { useMe, useRulesets } from '@/lib/api/hooks'
import { Empty, ErrorText, Mono, Select } from '@/components/ui'
import { PointsView } from './PointsView'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useSlashFocus } from '@/hooks/useSlashFocus'

/** Every hull in a ruleset with its class, size and points; opens on the team's active season. */
export function PointsPage() {
  usePageTitle('Points')
  useSlashFocus('points.filter.text')
  const me = useMe()
  const rulesets = useRulesets()
  const [code, setCode] = useState('')
  useEffect(() => {
    if (code || !rulesets.data?.length) return
    const active = me.data?.team?.active_ruleset
    const fallback = rulesets.data.find((r) => r.has_point_table)?.code ?? rulesets.data[0].code
    setCode(active && rulesets.data.some((r) => r.code === active) ? active : fallback)
  }, [code, rulesets.data, me.data])
  const ruleset = rulesets.data?.find((r) => r.code === code)

  if (rulesets.isLoading) return <Empty>Loading rulesets…</Empty>
  if (rulesets.error) return <ErrorText error={rulesets.error} />
  if (!ruleset) return <Empty>No rulesets imported.</Empty>

  return (
    <div className="mx-auto max-w-4xl space-y-3">
      <div className="flex items-center gap-3">
        <span className="text-muted">Ruleset</span>
        <Select value={code} onChange={(e) => setCode(e.target.value)} data-testid="points.ruleset">
          {rulesets.data!.map((r) => (
            <option key={r.code} value={r.code}>
              {r.code}
              {r.has_point_table ? '' : ' (no point table)'}
            </option>
          ))}
        </Select>
        <Mono className="text-muted">
          cap {ruleset.point_cap} {'·'} {ruleset.fielded_pilots} pilots
        </Mono>
      </div>
      {ruleset.has_point_table ? <PointsView key={code} code={code} /> : <p className="text-warn">This ruleset has no point table.</p>}
    </div>
  )
}
