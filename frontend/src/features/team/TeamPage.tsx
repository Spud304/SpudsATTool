import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useAdmissionRules, useInvites, useMe, useMembers, useRoles, useTeamMutations } from '@/lib/api/hooks'
import type { RoleOut } from '@/lib/api/client'
import { Badge, Button, Checkbox, Empty, ErrorText, Field, Input, Mono, PageHeader, Panel, Select, Table } from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'

/** The roles a manager may hand out: every role except admin, which only admins assign. */
function assignable(roles: RoleOut[] | undefined, isAdmin: boolean): RoleOut[] {
  return (roles ?? []).filter((r) => !r.is_system || isAdmin)
}

export function TeamPage() {
  usePageTitle('Team')
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_members)
  const isAdmin = Boolean(me.data?.capabilities?.is_admin)
  const canEditRoles = Boolean(me.data?.capabilities?.manage_team)
  return (
    <>
      <PageHeader
        title="Team"
        context={<span>{canManage ? 'members, invites and admission rules' : 'members'}</span>}
        actions={
          canEditRoles ? (
            <Link to="/team/roles" className="text-accent" data-testid="team.roles.link">
              Roles and permissions
            </Link>
          ) : null
        }
      />
    <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
      <MembersPanel canManage={canManage} isAdmin={isAdmin} myUserId={me.data?.user_id ?? null} />
      {canManage ? (
        <div className="space-y-4">
          <InvitesPanel isAdmin={isAdmin} />
          <RulesPanel isAdmin={isAdmin} />
        </div>
      ) : null}
    </div>
    </>
  )
}

function statusTone(status: string) {
  return status === 'active' ? 'ok' : status === 'suspended' ? 'warn' : 'bad'
}

function MembersPanel({ canManage, isAdmin, myUserId }: { canManage: boolean; isAdmin: boolean; myUserId: number | null }) {
  const members = useMembers()
  const roles = useRoles()
  const options = assignable(roles.data?.roles, isAdmin)
  const { patchMember, removeMember } = useTeamMutations()
  return (
    <Panel title={`Members${members.data ? ` (${members.data.length})` : ''}`}>
      <ErrorText error={patchMember.error ?? removeMember.error} />
      {members.data?.length ? (
        <Table hover>
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
              const locked = m.role === 'admin' && !isAdmin // the system role: only admins touch it
              const self = m.user_id === myUserId
              const editable = canManage && !locked
              const roleEditable = editable && !self // nobody changes their own role or status
              return (
                <tr key={m.user_id} data-testid={`team.members.row.${m.user_id}`}>
                  <td className="font-medium">
                    {m.display_name}
                    {m.user_id === myUserId ? <span className="ml-1 text-muted">(you)</span> : null}
                  </td>
                  <td className="text-muted">{m.characters.map((c) => c.name).join(', ')}</td>
                  <td>
                    {roleEditable ? (
                      <Select data-testid="team.members.role" value={m.role} onChange={(e) => patchMember.mutate({ userId: m.user_id, body: { role: e.target.value, reason: 'role change' } })}>
                        {options.map((r) => (
                          <option key={r.slug} value={r.slug}>
                            {r.name}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <Badge tone="accent" testId="team.members.role">
                        {m.role_name}
                      </Badge>
                    )}
                  </td>
                  <td>
                    {editable ? (
                      <Checkbox data-testid="team.members.leadership" checked={m.is_leadership} onChange={(e) => patchMember.mutate({ userId: m.user_id, body: { is_leadership: e.target.checked, reason: 'leadership toggle' } })} />
                    ) : m.is_leadership ? (
                      <Badge tone="info">yes</Badge>
                    ) : null}
                  </td>
                  <td>
                    <Badge tone={statusTone(m.status)} testId="team.members.status">
                      {m.status}
                    </Badge>
                  </td>
                  <td className="text-muted">{m.source}</td>
                  {canManage ? (
                    <td className="text-right">
                      {m.status !== 'active' && !locked && !self ? (
                        <Button data-testid="team.members.reinstate" onClick={() => patchMember.mutate({ userId: m.user_id, body: { status: 'active', reason: 'reinstated' } })}>
                          Reinstate
                        </Button>
                      ) : m.user_id !== myUserId && !locked ? (
                        <Button
                          data-testid="team.members.remove"
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
  const roles = useRoles()
  const options = assignable(roles.data?.roles, isAdmin)
  const { createInvite, revokeInvite } = useTeamMutations()
  const [role, setRole] = useState('pilot')
  const [uses, setUses] = useState(1)
  const [hours, setHours] = useState(72)
  const [note, setNote] = useState('')
  const [copied, setCopied] = useState<number | null>(null)
  return (
    <Panel title="Invite links" testId="team.invites">
      <form
        className="mb-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          createInvite.mutate({ role, uses, expires_in_hours: hours, note }, { onSuccess: () => setNote('') })
        }}
      >
        <Field label="Role">
          <Select data-testid="team.invites.role" value={role} onChange={(e) => setRole(e.target.value)}>
            {options.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Uses">
          <Input data-testid="team.invites.uses" type="number" min={1} className="w-16" value={uses} onChange={(e) => setUses(Number(e.target.value))} />
        </Field>
        <Field label="Expires (h)">
          <Input data-testid="team.invites.expires" type="number" min={1} className="w-20" value={hours} onChange={(e) => setHours(Number(e.target.value))} />
        </Field>
        <Field label="Note">
          <Input data-testid="team.invites.note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="who it is for" />
        </Field>
        <Button data-testid="team.invites.create" type="submit" variant="primary" disabled={createInvite.isPending}>
          Create
        </Button>
      </form>
      <ErrorText error={createInvite.error} />
      {invites.data?.length ? (
        <Table hover>
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
              <tr key={inv.id} data-testid={`team.invites.row.${inv.id}`}>
                <td>
                  <Badge tone="accent">{inv.role_name}</Badge>
                </td>
                <td>
                  <Mono>{inv.uses_left}</Mono>
                </td>
                <td className="text-muted">{new Date(inv.expires_at).toLocaleString()}</td>
                <td className="text-muted">{inv.note}</td>
                <td className="whitespace-nowrap text-right">
                  <Button
                    data-testid="team.invites.copy"
                    onClick={() => {
                      void navigator.clipboard.writeText(inv.url)
                      setCopied(inv.id)
                      setTimeout(() => setCopied(null), 1500)
                    }}
                  >
                    {copied === inv.id ? 'Copied' : 'Copy link'}
                  </Button>{' '}
                  <Button data-testid="team.invites.revoke" variant="ghost" onClick={() => revokeInvite.mutate(inv.id)}>
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
  const roles = useRoles()
  const options = assignable(roles.data?.roles, isAdmin)
  const { createRule, patchRule, deleteRule } = useTeamMutations()
  const [kind, setKind] = useState<'corporation' | 'alliance'>('alliance')
  const [entityId, setEntityId] = useState('')
  const [entityName, setEntityName] = useState('')
  const [role, setRole] = useState('pilot')
  return (
    <Panel title="Admission rules" testId="team.rules">
      <p className="mb-2 text-body text-muted">
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
          <Select data-testid="team.rules.kind" value={kind} onChange={(e) => setKind(e.target.value as 'corporation' | 'alliance')}>
            <option value="alliance">Alliance</option>
            <option value="corporation">Corporation</option>
          </Select>
        </Field>
        <Field label="ID">
          <Input data-testid="team.rules.id" className="w-32" value={entityId} onChange={(e) => setEntityId(e.target.value)} />
        </Field>
        <Field label="Name (optional)">
          <Input data-testid="team.rules.name" value={entityName} onChange={(e) => setEntityName(e.target.value)} />
        </Field>
        <Field label="Role">
          <Select data-testid="team.rules.role" value={role} onChange={(e) => setRole(e.target.value)}>
            {options.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.name}
              </option>
            ))}
          </Select>
        </Field>
        <Button data-testid="team.rules.add" type="submit" variant="primary" disabled={createRule.isPending || !entityId}>
          Add
        </Button>
      </form>
      <ErrorText error={createRule.error} />
      {rules.data?.length ? (
        <Table hover>
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
              <tr key={r.id} data-testid={`team.rules.row.${r.id}`}>
                <td>{r.kind}</td>
                <td>
                  {r.entity_name || <span className="text-muted">unnamed</span>} <Mono className="text-muted">{r.entity_id}</Mono>
                </td>
                <td>
                  <Badge tone="accent">{r.default_role_name}</Badge>
                </td>
                <td>
                  <Checkbox data-testid="team.rules.enabled" checked={r.enabled} onChange={(e) => patchRule.mutate({ id: r.id, enabled: e.target.checked })} />
                </td>
                <td className="text-right">
                  <Button data-testid="team.rules.delete" variant="ghost" onClick={() => deleteRule.mutate(r.id)}>
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
