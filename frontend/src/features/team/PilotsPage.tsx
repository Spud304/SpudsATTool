import { useState } from 'react'
import { useMe, useMembers, useOpponents, usePilots, useRosterMutations } from '@/lib/api/hooks'
import type { OpponentOut, PilotOut } from '@/lib/api/client'
import { Badge, Button, Checkbox, Empty, ErrorText, Field, Input, Panel, Select, Table } from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'

/** Roster and opponent registry. Members with role pilot or above appear here on their own; mercs are added by hand. */
export function PilotsPage() {
  usePageTitle('Pilots')
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_scrims)
  return (
    <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
      <RosterPanel canManage={canManage} />
      <OpponentsPanel canManage={canManage} />
    </div>
  )
}

function RosterPanel({ canManage }: { canManage: boolean }) {
  const pilots = usePilots()
  const members = useMembers()
  const { createPilot, patchPilot } = useRosterMutations()
  const [name, setName] = useState('')
  const [merc, setMerc] = useState(false)
  const [roles, setRoles] = useState('')
  const linked = new Set((pilots.data ?? []).map((p) => p.user_id).filter((id): id is number => id !== null))
  return (
    <Panel title={`Roster${pilots.data ? ` (${pilots.data.length})` : ''}`} testId="pilots">
      <ErrorText error={patchPilot.error} />
      {pilots.data?.length ? (
        <Table>
          <thead>
            <tr>
              <th>Pilot</th>
              <th>Login</th>
              <th>Merc</th>
              <th>Roles</th>
              <th>Status</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {pilots.data.map((p) => (
              <PilotRow
                key={p.id}
                pilot={p}
                canManage={canManage}
                members={(members.data ?? []).filter((m) => m.user_id === p.user_id || !linked.has(m.user_id)).map((m) => ({ id: m.user_id, name: m.display_name }))}
                onPatch={(body) => patchPilot.mutate({ id: p.id, body })}
              />
            ))}
          </tbody>
        </Table>
      ) : pilots.isLoading ? (
        <Empty>Loading…</Empty>
      ) : (
        <Empty>No pilots yet.</Empty>
      )}
      {canManage ? (
        <form
          className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3"
          onSubmit={(e) => {
            e.preventDefault()
            createPilot.mutate(
              { name: name.trim(), is_merc: merc, roles_text: roles.trim(), notes: '', user_id: null },
              {
                onSuccess: () => {
                  setName('')
                  setRoles('')
                  setMerc(false)
                },
              },
            )
          }}
        >
          <Field label="New pilot">
            <Input data-testid="pilots.new.name" value={name} onChange={(e) => setName(e.target.value)} placeholder="character name" />
          </Field>
          <Field label="Roles">
            <Input data-testid="pilots.new.roles" value={roles} onChange={(e) => setRoles(e.target.value)} placeholder="logi, tackle" className="w-36" />
          </Field>
          <label className="flex h-7 items-center gap-1 text-[12px]">
            <Checkbox data-testid="pilots.new.merc" checked={merc} onChange={(e) => setMerc(e.target.checked)} /> merc
          </label>
          <Button data-testid="pilots.new.create" type="submit" variant="primary" disabled={!name.trim() || createPilot.isPending}>
            Add pilot
          </Button>
          <ErrorText error={createPilot.error} testId="pilots.new.error" />
        </form>
      ) : null}
    </Panel>
  )
}

function PilotRow({
  pilot,
  canManage,
  members,
  onPatch,
}: {
  pilot: PilotOut
  canManage: boolean
  members: { id: number; name: string }[]
  onPatch: (body: { user_id?: number | null; is_merc?: boolean; roles_text?: string; status?: string; notes?: string }) => void
}) {
  const [roles, setRoles] = useState(pilot.roles_text)
  const [notes, setNotes] = useState(pilot.notes)
  const id = `pilots.row.${pilot.id}`
  return (
    <tr data-testid={id}>
      <td className="font-medium" data-testid={`${id}.name`}>
        {pilot.name}
      </td>
      <td>
        {canManage ? (
          <Select data-testid={`${id}.user`} value={pilot.user_id ?? ''} onChange={(e) => onPatch({ user_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">no login</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </Select>
        ) : pilot.user_name ? (
          <span className="text-muted">{pilot.user_name}</span>
        ) : (
          <Badge>no login</Badge>
        )}
      </td>
      <td>{canManage ? <Checkbox data-testid={`${id}.merc`} checked={pilot.is_merc} onChange={(e) => onPatch({ is_merc: e.target.checked })} /> : pilot.is_merc ? <Badge tone="info">merc</Badge> : null}</td>
      <td>
        {canManage ? (
          <Input data-testid={`${id}.roles`} className="w-36" value={roles} onChange={(e) => setRoles(e.target.value)} onBlur={() => roles !== pilot.roles_text && onPatch({ roles_text: roles })} />
        ) : (
          <span className="text-muted">{pilot.roles_text}</span>
        )}
      </td>
      <td>
        {canManage ? (
          <Select data-testid={`${id}.status`} value={pilot.status} onChange={(e) => onPatch({ status: e.target.value })}>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
          </Select>
        ) : (
          <Badge tone={pilot.status === 'active' ? 'ok' : 'muted'}>{pilot.status}</Badge>
        )}
      </td>
      <td>
        {canManage ? (
          <Input data-testid={`${id}.notes`} className="w-48" value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== pilot.notes && onPatch({ notes })} />
        ) : (
          <span className="text-muted">{pilot.notes}</span>
        )}
      </td>
    </tr>
  )
}

function OpponentsPanel({ canManage }: { canManage: boolean }) {
  const opponents = useOpponents()
  const { createOpponent, patchOpponent } = useRosterMutations()
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  return (
    <Panel title={`Opponents${opponents.data ? ` (${opponents.data.length})` : ''}`} testId="opponents">
      <ErrorText error={patchOpponent.error} />
      {opponents.data?.length ? (
        <Table>
          <thead>
            <tr>
              <th>Team</th>
              <th>Notes</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {opponents.data.map((o) => (
              <OpponentRow key={o.id} opponent={o} canManage={canManage} onPatch={(body) => patchOpponent.mutate({ id: o.id, body })} />
            ))}
          </tbody>
        </Table>
      ) : (
        <Empty>No opponents yet.</Empty>
      )}
      {canManage ? (
        <form
          className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3"
          onSubmit={(e) => {
            e.preventDefault()
            createOpponent.mutate(
              { name: name.trim(), notes: notes.trim(), alliance_id: null },
              {
                onSuccess: () => {
                  setName('')
                  setNotes('')
                },
              },
            )
          }}
        >
          <Field label="New opponent">
            <Input data-testid="opponents.new.name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Notes">
            <Input data-testid="opponents.new.notes" value={notes} onChange={(e) => setNotes(e.target.value)} className="w-48" />
          </Field>
          <Button data-testid="opponents.new.create" type="submit" variant="primary" disabled={!name.trim() || createOpponent.isPending}>
            Add opponent
          </Button>
          <ErrorText error={createOpponent.error} testId="opponents.new.error" />
        </form>
      ) : null}
    </Panel>
  )
}

function OpponentRow({ opponent, canManage, onPatch }: { opponent: OpponentOut; canManage: boolean; onPatch: (body: { notes?: string; is_active?: boolean }) => void }) {
  const [notes, setNotes] = useState(opponent.notes)
  const id = `opponents.row.${opponent.id}`
  return (
    <tr data-testid={id}>
      <td className="font-medium">{opponent.name}</td>
      <td>
        {canManage ? (
          <Input data-testid={`${id}.notes`} className="w-full" value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== opponent.notes && onPatch({ notes })} />
        ) : (
          <span className="text-muted">{opponent.notes}</span>
        )}
      </td>
      <td>{canManage ? <Checkbox data-testid={`${id}.active`} checked={opponent.is_active} onChange={(e) => onPatch({ is_active: e.target.checked })} /> : <Badge tone={opponent.is_active ? 'ok' : 'muted'}>{opponent.is_active ? 'yes' : 'no'}</Badge>}</td>
    </tr>
  )
}
