import { useState } from 'react'
import { useAudit } from '@/lib/api/hooks'
import { Button, Empty, ErrorText, Input, Mono, Panel, Table } from '@/components/ui'

const PAGE = 50

export function AuditPage() {
  const [action, setAction] = useState('')
  const [offset, setOffset] = useState(0)
  const audit = useAudit({ action: action || undefined, limit: PAGE, offset })
  const items = audit.data?.items ?? []
  const count = audit.data?.count ?? 0
  return (
    <Panel
      title={`Audit log${count ? ` (${count})` : ''}`}
      actions={
        <div className="flex items-center gap-2">
          <Input
            data-testid="audit.filter"
            placeholder="filter by action, e.g. membership.removed"
            className="w-72"
            value={action}
            onChange={(e) => {
              setAction(e.target.value)
              setOffset(0)
            }}
          />
          <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Prev
          </Button>
          <Button disabled={offset + PAGE >= count} onClick={() => setOffset(offset + PAGE)}>
            Next
          </Button>
        </div>
      }
    >
      <ErrorText error={audit.error} />
      {items.length ? (
        <Table>
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
      ) : (
        <Empty>Nothing recorded yet.</Empty>
      )}
    </Panel>
  )
}
