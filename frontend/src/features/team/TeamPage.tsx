import { useState } from 'react'
import { useAdmissionRules, useInvites, useMe, useMembers, useTeamMutations } from '@/lib/api/hooks'
import type { Role } from '@/lib/api/client'
import { Badge, Button, Checkbox, Empty, ErrorText, Field, Input, Mono, Panel, Select, Table } from '@/components/ui'

const ROLES: Role[] = ['admin', 'captain', 'theorycrafter', 'pilot', 'guest', 'viewer']

export function TeamPage() {
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_members)
  const isAdmin = me.data?.membership?.role === 'admin'
  return (
    <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
      <MembersPanel canManage={canManage} isAdmin={isAdmin} myUserId={me.data?.user_id ?? null} />
      {canManage ? (
        <div className="space-y-4">
          <InvitesPanel isAdmin={isAdmin} />
          <RulesPanel isAdmin={isAdmin} />
        </div>
      ) : null}
    </div>
  )
}

function statusTone(status: string) {
  return status === 'active' ? 'ok' : status === 'suspended' ? 'warn' : 'bad'
}

function MembersPanel({ canManage, isAdmin, myUserId }: { canManage: boolean; isAdmin: boolean; myUserId: number | null }) {
  const members = useMembers()
  const { patchMember, removeMember } = useTeamMutations()
  return (
    <Panel title={`Members${members.data ? ` (${members.data.length})` : ''}`}>
      <ErrorText error={patchMember.error ?? removeMember.error} />
      {members.data?.length ? (
        <Table>
          <thead>
            <tr>
              <th>Member</th>
              <th>Characters</th>
              <th>Role</th>
              <th>Leadership</th>
              <th>Status</th>
              <th>Source</th>
              {canManage ? <th /> : null}
            </tr>
          </thead>
          <tbody>
            {members.data.map((m) => {
              const locked = m.role === 'admin' && !isAdmin
              const editable = canManage && !locked
              return (
                <tr key={m.user_id}>
                  <td className="font-medium">
                    {m.display_name}
                    {m.user_id === myUserId ? <span className="ml-1 text-muted">(you)</span> : null}
                  </td>
                  <td className="text-muted">{m.characters.map((c) => c.name).join(', ')}</td>
                  <td>
                    {editable ? (
                      <Select value={m.role} onChange={(e) => patchMember.mutate({ userId: m.user_id, body: { role: e.target.value as Role, reason: 'role change' } })}>
                        {ROLES.filter((r) => r !== 'admin' || isAdmin).map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <Badge tone="accent">{m.role}</Badge>
                    )}
                  </td>
                  <td>
                    {editable ? (
                      <Checkbox checked={m.is_leadership} onChange={(e) => patchMember.mutate({ userId: m.user_id, body: { is_leadership: e.target.checked, reason: 'leadership toggle' } })} />
                    ) : m.is_leadership ? (
                      <Badge tone="info">yes</Badge>
                    ) : null}
                  </td>
                  <td>
                    <Badge tone={statusTone(m.status)}>{m.status}</Badge>
                  </td>
                  <td className="text-muted">{m.source}</td>
                  {canManage ? (
                    <td className="text-right">
                      {m.status !== 'active' && !locked ? (
                        <Button onClick={() => patchMember.mutate({ userId: m.user_id, body: { status: 'active', reason: 'reinstated' } })}>Reinstate</Button>
                      ) : m.user_id !== myUserId && !locked ? (
                        <Button
                          variant="danger"
                          onClick={() => {
                            const reason = window.prompt('Reason for removing this member (kept in the audit log):')
                            if (reason !== null) removeMember.mutate({ userId: m.user_id, reason })
                          }}
                        >
                          Remove
                        </Button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              )
            })}
          </tbody>
        </Table>
      ) : members.isLoading ? (
        <Empty>Loading…</Empty>
      ) : (
        <Empty>No members yet.</Empty>
      )}
    </Panel>
  )
}

function InvitesPanel({ isAdmin }: { isAdmin: boolean }) {
  const invites = useInvites()
  const { createInvite, revokeInvite } = useTeamMutations()
  const [role, setRole] = useState<Role>('pilot')
  const [uses, setUses] = useState(1)
  const [hours, setHours] = useState(72)
  const [note, setNote] = useState('')
  const [copied, setCopied] = useState<number | null>(null)
  return (
    <Panel title="Invite links">
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          createInvite.mutate({ role, uses, expires_in_hours: hours, note }, { onSuccess: () => setNote('') })
        }}
      >
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.filter((r) => r !== 'admin' || isAdmin).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Uses">
          <Input type="number" min={1} className="w-16" value={uses} onChange={(e) => setUses(Number(e.target.value))} />
        </Field>
        <Field label="Expires (h)">
          <Input type="number" min={1} className="w-20" value={hours} onChange={(e) => setHours(Number(e.target.value))} />
        </Field>
        <Field label="Note">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="who it is for" />
        </Field>
        <Button type="submit" variant="primary" disabled={createInvite.isPending}>
          Create
        </Button>
      </form>
      <ErrorText error={createInvite.error} />
      {invites.data?.length ? (
        <Table>
          <thead>
            <tr>
              <th>Role</th>
              <th>Uses</th>
              <th>Expires</th>
              <th>Note</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {invites.data.map((inv) => (
              <tr key={inv.id}>
                <td>
                  <Badge tone="accent">{inv.role}</Badge>
                </td>
                <td>
                  <Mono>{inv.uses_left}</Mono>
                </td>
                <td className="text-muted">{new Date(inv.expires_at).toLocaleString()}</td>
                <td className="text-muted">{inv.note}</td>
                <td className="whitespace-nowrap text-right">
                  <Button
                    onClick={() => {
                      void navigator.clipboard.writeText(inv.url)
                      setCopied(inv.id)
                      setTimeout(() => setCopied(null), 1500)
                    }}
                  >
                    {copied === inv.id ? 'Copied' : 'Copy link'}
                  </Button>{' '}
                  <Button variant="ghost" onClick={() => revokeInvite.mutate(inv.id)}>
                    Revoke
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <Empty>No active invites.</Empty>
      )}
    </Panel>
  )
}

function RulesPanel({ isAdmin }: { isAdmin: boolean }) {
  const rules = useAdmissionRules()
  const { createRule, patchRule, deleteRule } = useTeamMutations()
  const [kind, setKind] = useState<'corporation' | 'alliance'>('alliance')
  const [entityId, setEntityId] = useState('')
  const [entityName, setEntityName] = useState('')
  const [role, setRole] = useState<Role>('pilot')
  return (
    <Panel title="Admission rules">
      <p className="mb-2 text-[12px] text-muted">
        Characters in these corporations or alliances are admitted automatically. Re-checked hourly; members who leave are suspended after the grace period.
      </p>
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (!entityId) return
          createRule.mutate(
            { kind, entity_id: Number(entityId), entity_name: entityName, default_role: role, enabled: true },
            {
              onSuccess: () => {
                setEntityId('')
                setEntityName('')
              },
            },
          )
        }}
      >
        <Field label="Kind">
          <Select value={kind} onChange={(e) => setKind(e.target.value as 'corporation' | 'alliance')}>
            <option value="alliance">Alliance</option>
            <option value="corporation">Corporation</option>
          </Select>
        </Field>
        <Field label="ID">
          <Input className="w-32" value={entityId} onChange={(e) => setEntityId(e.target.value)} />
        </Field>
        <Field label="Name (optional)">
          <Input value={entityName} onChange={(e) => setEntityName(e.target.value)} />
        </Field>
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.filter((r) => r !== 'admin' || isAdmin).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" variant="primary" disabled={createRule.isPending || !entityId}>
          Add
        </Button>
      </form>
      <ErrorText error={createRule.error} />
      {rules.data?.length ? (
        <Table>
          <thead>
            <tr>
              <th>Kind</th>
              <th>Entity</th>
              <th>Role</th>
              <th>Enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rules.data.map((r) => (
              <tr key={r.id}>
                <td>{r.kind}</td>
                <td>
                  {r.entity_name || <span className="text-muted">unnamed</span>} <Mono className="text-muted">{r.entity_id}</Mono>
                </td>
                <td>
                  <Badge tone="accent">{r.default_role}</Badge>
                </td>
                <td>
                  <Checkbox checked={r.enabled} onChange={(e) => patchRule.mutate({ id: r.id, enabled: e.target.checked })} />
                </td>
                <td className="text-right">
                  <Button variant="ghost" onClick={() => deleteRule.mutate(r.id)}>
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : (
        <Empty>No rules. Members join by invite link only.</Empty>
      )}
    </Panel>
  )
}
