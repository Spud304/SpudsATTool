import { Fragment, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useFits } from '@/lib/api/hooks'
import type { FitSummaryOut } from '@/lib/api/client'
import { Badge, Button, Empty, ErrorText, Input, Mono, PageHeader, Panel, Select, Table } from '@/components/ui'
import { NewFitPanel } from './NewFitPanel'
import { num, statusTone, when } from './format'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useSlashFocus } from '@/hooks/useSlashFocus'

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: 'active,suggested', label: 'Active + suggested' },
  { value: 'active', label: 'Active' },
  { value: 'suggested', label: 'Suggested' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'retired', label: 'Retired' },
  { value: '', label: 'All' },
]

export function FitsPage() {
  usePageTitle('Fits')
  useSlashFocus('fits.search')
  const [status, setStatus] = useState('active,suggested')
  const [q, setQ] = useState('')
  const fits = useFits({ status: status || undefined, q: q.trim() || undefined })
  const groups = groupByHull(fits.data ?? [])
  const [closed, setClosed] = useState<Record<string, boolean>>({}) // hull groups fold on a header click
  return (
    <>
      <PageHeader title="Fits" count={fits.data ? fits.data.length : undefined} actions={
          <div className="flex items-center gap-2">
            <Input data-testid="fits.search" placeholder="search hull or fit" className="w-56" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select data-testid="fits.status" value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_FILTERS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
            <Button data-testid="fits.expand" className="h-6 px-2" onClick={() => setClosed({})}>
              Expand all
            </Button>
            <Button data-testid="fits.collapse" className="h-6 px-2" onClick={() => setClosed(Object.fromEntries(groups.map(([hull]) => [hull, true])))}>
              Collapse all
            </Button>
          </div>
      } />
    <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
      <Panel>
        <ErrorText error={fits.error} />
        {groups.length ? (
          <Table hover>
            <thead>
              <tr>
                <th>Fit</th>
                <th>Status</th>
                <th className="text-right">DPS</th>
                <th className="text-right">EHP k</th>
                <th className="text-right">m/s</th>
                <th>Flags</th>
                <th>By</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {groups.map(([hull, rows]) => (
                <Fragment key={hull}>
                  <tr>
                    <td colSpan={8} className="bg-panel-2 p-0 font-semibold">
                      <button type="button" data-testid={`fits.group.${hull}`} onClick={() => setClosed((c) => ({ ...c, [hull]: !c[hull] }))} className="flex w-full items-center gap-1.5 px-2 py-1 text-left hover:text-accent">
                        <span className="text-[10px] text-muted">{closed[hull] ? '▸' : '▾'}</span>
                        {hull} <span className="text-muted">({rows.length})</span>
                      </button>
                    </td>
                  </tr>
                  {closed[hull] ? null : rows.map((f) => (
                    <tr key={f.id} data-testid={`fits.row.${f.id}`}>
                      <td>
                        <Link to="/fits/$fitId" params={{ fitId: String(f.id) }} className="inline-block max-w-xs truncate align-bottom text-accent hover:underline" title={f.name}>
                          {f.name}
                        </Link>
                      </td>
                      <td>
                        <Badge tone={statusTone(f.status)}>{f.status}</Badge>
                      </td>
                      <td className="text-right">
                        <Mono>{num(f.dps)}</Mono>
                      </td>
                      <td className="text-right">
                        <Mono>{num(f.ehp_k, 1)}</Mono>
                      </td>
                      <td className="text-right">
                        <Mono>{num(f.speed_ms)}</Mono>
                      </td>
                      <td className="space-x-1">
                        {f.has_links ? <Badge tone="accent">links</Badge> : null}
                        {!f.stats_parse_ok ? <Badge tone="muted">no stats</Badge> : null}
                        {f.unresolved_count ? <Badge tone="warn">{f.unresolved_count} unknown</Badge> : null}
                      </td>
                      <td className="text-muted">{f.created_by_name || 'import'}</td>
                      <td className="text-muted">{when(f.updated_at)}</td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </Table>
        ) : fits.isLoading ? (
          <Empty>Loading…</Empty>
        ) : (
          <Empty
            testId="fits.empty"
            hint={status !== 'active,suggested' || q ? undefined : 'Paste an EFT block on the right to add the first one.'}
            action={
              status !== 'active,suggested' || q ? (
                <Button
                  data-testid="fits.clear"
                  onClick={() => {
                    setStatus('active,suggested')
                    setQ('')
                  }}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          >
            No fits match these filters.
          </Empty>
        )}
      </Panel>
      <NewFitPanel />
    </div>
    </>
  )
}

function groupByHull(fits: FitSummaryOut[]): [string, FitSummaryOut[]][] {
  const map = new Map<string, FitSummaryOut[]>()
  for (const f of fits) {
    const list = map.get(f.ship_name)
    if (list) list.push(f)
    else map.set(f.ship_name, [f])
  }
  return [...map.entries()]
}
