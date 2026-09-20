import { useState } from 'react'
import { useAudit, useAuditFacets } from '@/lib/api/hooks'
import { Button, Empty, ErrorText, Input, Mono, PageHeader, Panel, Select, Table } from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useSlashFocus } from '@/hooks/useSlashFocus'

const PAGE = 50

type Filters = { actor_id: string; action: string; target_type: string; since: string; until: string; q: string }
const EMPTY: Filters = { actor_id: '', action: '', target_type: '', since: '', until: '', q: '' }

/** Who did what, when and why. Filters narrow by member, action, target type, date range and free text. */
export function AuditPage() {
  usePageTitle('Audit')
  useSlashFocus('audit.filter')
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [offset, setOffset] = useState(0)
  const facets = useAuditFacets()
  const audit = useAudit({
    actor_id: filters.actor_id ? Number(filters.actor_id) : undefined,
    action: filters.action || undefined,
    target_type: filters.target_type || undefined,
    since: filters.since || undefined,
    until: filters.until || undefined,
    q: filters.q || undefined,
    limit: PAGE,
    offset,
  })
  const items = audit.data?.items ?? []
  const count = audit.data?.count ?? 0
  const active = Object.values(filters).some(Boolean)
  const update = (patch: Partial<Filters>) => {
    setFilters({ ...filters, ...patch })
    setOffset(0)
  }

  return (
    <>
      <PageHeader
        title="Audit log"
        count={audit.data ? `${count} ${active ? 'matching' : 'entries'}` : undefined}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select data-testid="audit.filter.actor" value={filters.actor_id} onChange={(e) => update({ actor_id: e.target.value })}>
              <option value="">anyone</option>
              {(facets.data?.actors ?? []).map((a) => (
                <option key={a.user_id} value={a.user_id}>
                  {a.display_name}
                </option>
              ))}
            </Select>
            <Input
              data-testid="audit.filter"
              list="audit-actions"
              placeholder="action, e.g. membership.removed"
              className="w-56"
              value={filters.action}
              onChange={(e) => update({ action: e.target.value })}
            />
            <datalist id="audit-actions">
              {(facets.data?.actions ?? []).map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
            <Select data-testid="audit.filter.target" value={filters.target_type} onChange={(e) => update({ target_type: e.target.value })}>
              <option value="">any target</option>
              {(facets.data?.target_types ?? []).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
            <Input data-testid="audit.filter.since" type="date" className="w-36" value={filters.since} onChange={(e) => update({ since: e.target.value })} title="from this day" />
            <Input data-testid="audit.filter.until" type="date" className="w-36" value={filters.until} onChange={(e) => update({ until: e.target.value })} title="up to and including this day" />
            <Input data-testid="audit.filter.q" placeholder="target or reason" className="w-40" value={filters.q} onChange={(e) => update({ q: e.target.value })} />
            {active ? (
              <Button data-testid="audit.clear" onClick={() => update(EMPTY)}>
                Clear filters
              </Button>
            ) : null}
            <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Prev
            </Button>
            <Button disabled={offset + PAGE >= count} onClick={() => setOffset(offset + PAGE)}>
              Next
            </Button>
          </div>
        }
      />
      <Panel>
        <ErrorText error={audit.error} />
        {items.length ? (
          <Table hover>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>Target</th>
                <th>Reason</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} data-testid="audit.row">
                  <td className="whitespace-nowrap text-muted">
                    <Mono>{new Date(e.at).toLocaleString()}</Mono>
                  </td>
                  <td>{e.actor_name}</td>
                  <td>
                    <Mono>{e.action}</Mono>
                  </td>
                  <td>
                    {e.target_label} <span className="text-muted">{e.target_type}</span>
                  </td>
                  <td className="text-muted">{e.reason}</td>
                  <td className="max-w-md truncate text-[11px] text-muted" title={JSON.stringify({ before: e.before, after: e.after })}>
                    <Mono>{e.after ? JSON.stringify(e.after) : ''}</Mono>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : audit.isLoading ? (
          <Empty>Loading…</Empty>
        ) : active ? (
          <Empty
            action={
              <Button data-testid="audit.clear.empty" onClick={() => update(EMPTY)}>
                Clear filters
              </Button>
            }
          >
            Nothing matches these filters.
          </Empty>
        ) : (
          <Empty hint="Membership, role, library and scrim changes land here with who did them and why.">Nothing recorded yet.</Empty>
        )}
      </Panel>
    </>
  )
}
