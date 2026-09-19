import { useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useMe, useScrim, useScrimMutations, useScrims } from '@/lib/api/hooks'
import type { SessionSummaryOut } from '@/lib/api/client'
import { Badge, Button, Empty, ErrorText, Mono, Panel, Table } from '@/components/ui'
import { RsvpButtons } from './RsvpButtons'
import { SessionForm } from './SessionForm'
import { RSVP_LABELS, record, rsvpTone, whenAt } from './format'

export function ScrimsPage() {
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_scrims)
  const upcoming = useScrims('upcoming')
  const past = useScrims('past')

  return (
    <div className="grid gap-4 xl:grid-cols-[3fr_1fr]">
      <div className="space-y-4">
        <Panel title={`Upcoming${upcoming.data ? ` (${upcoming.data.length})` : ''}`} testId="scrims.upcoming">
          <ErrorText error={upcoming.error} />
          {upcoming.data?.length ? (
            <ul className="divide-y divide-line">
              {upcoming.data.map((s) => (
                <UpcomingRow key={s.id} scrim={s} canManage={canManage} />
              ))}
            </ul>
          ) : upcoming.isLoading ? (
            <Empty>Loading…</Empty>
          ) : (
            <Empty testId="scrims.upcoming.empty" hint={canManage ? 'Use the New scrim panel to schedule the next night.' : 'Captains add scrims here; you will see RSVP buttons once one is up.'}>
              Nothing scheduled.
            </Empty>
          )}
        </Panel>
        <Panel title={`Past${past.data ? ` (${past.data.length})` : ''}`} testId="scrims.past">
          {past.data?.length ? (
            <Table>
              <thead>
                <tr>
                  <th>Scrim</th>
                  <th>When</th>
                  <th>Opponent</th>
                  <th>Kind</th>
                  <th>Sets</th>
                  <th>Record</th>
                  <th>Turnout</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {past.data.map((s) => (
                  <tr key={s.id} data-testid={`scrims.past.row.${s.id}`}>
                    <td>
                      <Link to="/scrims/$scrimId" params={{ scrimId: String(s.id) }} className="text-accent hover:underline">
                        {s.title}
                      </Link>
                    </td>
                    <td className="text-muted">{whenAt(s.date)}</td>
                    <td>{s.opponent_name ?? ''}</td>
                    <td className="text-muted">{s.kind.replace('_', ' ')}</td>
                    <td>
                      <Mono>{s.sets.length}</Mono>
                    </td>
                    <td>
                      <Mono>{record(s.sets)}</Mono>
                    </td>
                    <td>
                      <Mono className="text-muted">{s.tally.yes} yes</Mono>
                    </td>
                    <td>{s.is_archived ? <Badge tone="muted">archived</Badge> : null}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <Empty hint="Results, records and turnout appear here after the first night.">No past scrims yet.</Empty>
          )}
        </Panel>
      </div>
      {canManage ? <NewScrimPanel /> : null}
    </div>
  )
}

function UpcomingRow({ scrim, canManage }: { scrim: SessionSummaryOut; canManage: boolean }) {
  const [open, setOpen] = useState(false)
  const t = scrim.tally
  return (
    <li className="py-2" data-testid={`scrims.row.${scrim.id}`}>
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/scrims/$scrimId" params={{ scrimId: String(scrim.id) }} className="font-medium text-accent hover:underline" data-testid={`scrims.row.${scrim.id}.title`}>
          {scrim.title}
        </Link>
        <span className="text-muted">{whenAt(scrim.date)}</span>
        {scrim.opponent_name ? <span>vs {scrim.opponent_name}</span> : null}
        <Badge>{scrim.kind.replace('_', ' ')}</Badge>
        {scrim.stage ? <Badge tone="info">{scrim.stage}</Badge> : null}
        {scrim.system_name ? <Mono className="text-muted">{scrim.system_name}</Mono> : null}
        <span className="ml-auto flex items-center gap-1 text-[11px]" data-testid={`scrims.row.${scrim.id}.tally`} title="yes / maybe / no / no answer">
          <Badge tone="ok">{t.yes}</Badge>
          <Badge tone="warn">{t.maybe}</Badge>
          <Badge tone="bad">{t.no}</Badge>
          <Badge>{t.none}</Badge>
        </span>
        {canManage ? (
          <Button variant="ghost" data-testid={`scrims.row.${scrim.id}.rollcall`} onClick={() => setOpen((v) => !v)}>
            {open ? 'hide roll call' : 'roll call'}
          </Button>
        ) : null}
      </div>
      <div className="mt-1">
        <RsvpButtons scrim={scrim} testPrefix={`scrims.row.${scrim.id}`} />
      </div>
      {open ? <RollCall scrimId={scrim.id} /> : null}
    </li>
  )
}

/** Who said what, grouped by answer; reasons inline. Loads the full session on demand. */
function RollCall({ scrimId }: { scrimId: number }) {
  const scrim = useScrim(scrimId)
  if (!scrim.data) return <p className="mt-2 text-[11px] text-muted">Loading…</p>
  const groups = ['yes', 'maybe', 'none', 'no']
  return (
    <div className="mt-2 grid gap-2 rounded border border-line bg-bg p-2 text-[12px] md:grid-cols-4" data-testid={`scrims.row.${scrimId}.rollcall.list`}>
      {groups.map((g) => {
        const rows = scrim.data.attendance.filter((a) => a.rsvp === g)
        return (
          <div key={g}>
            <div className="mb-1">
              <Badge tone={rsvpTone(g)}>
                {RSVP_LABELS[g]} · {rows.length}
              </Badge>
            </div>
            <ul className="space-y-0.5">
              {rows.map((a) => (
                <li key={a.pilot_id} data-testid={`scrims.row.${scrimId}.rollcall.${a.pilot_id}`}>
                  {a.pilot_name}
                  {a.rsvp_reason ? <span className="text-muted"> · {a.rsvp_reason}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

function NewScrimPanel() {
  const navigate = useNavigate()
  const { createScrim } = useScrimMutations()
  return (
    <Panel title="New scrim" testId="scrims.new">
      <SessionForm
        submitLabel="Create scrim"
        pending={createScrim.isPending}
        error={createScrim.error}
        testPrefix="scrims.new"
        onSubmit={(payload) =>
          createScrim.mutate(payload, {
            onSuccess: (session) => void navigate({ to: '/scrims/$scrimId', params: { scrimId: String(session.id) } }),
          })
        }
      />
    </Panel>
  )
}
