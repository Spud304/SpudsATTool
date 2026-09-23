import { useMemo, useState } from 'react'
import clsx from 'clsx'
import type { RoleOut } from '@/lib/api/client'
import { useMe, useRoleMutations, useRoles } from '@/lib/api/hooks'
import { Badge, Button, Checkbox, Empty, ErrorText, Field, Input, Mono, PageHeader, Panel, Select, Table } from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'

/** Roles as a matrix: one row per role, one column per permission, grouped. Admins tick and untick. */
export function RolesPage() {
  usePageTitle('Roles')
  const me = useMe()
  const roles = useRoles()
  const canEdit = Boolean(me.data?.capabilities?.manage_team)
  const { createRole, patchRole, deleteRole } = useRoleMutations()
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [copyFrom, setCopyFrom] = useState('')
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null)

  const groups = useMemo(() => {
    const out = new Map<string, RoleOut['permissions']>()
    for (const p of roles.data?.catalog ?? []) out.set(p.group, [...(out.get(p.group) ?? []), p.code])
    return [...out.entries()]
  }, [roles.data])
  const catalog = useMemo(() => new Map((roles.data?.catalog ?? []).map((p) => [p.code, p])), [roles.data])

  if (roles.error) return <ErrorText error={roles.error} />
  if (!roles.data) return <Empty>Loading…</Empty>
  const rows = roles.data.roles

  const toggle = (role: RoleOut, code: string, on: boolean) => {
    const next = on ? [...role.permissions, code] : role.permissions.filter((c) => c !== code)
    patchRole.mutate({ id: role.id, body: { permissions: next, reason: `${on ? 'granted' : 'removed'} ${code}` } })
  }
  const remove = (role: RoleOut) => {
    // Only an admin may move members into the admin role (the server refuses anyone else).
    const isAdmin = Boolean(me.data?.capabilities?.is_admin)
    const others = rows.filter((r) => r.id !== role.id && (!r.is_system || isAdmin))
    let target: RoleOut | undefined
    if (role.member_count > 0) {
      const suggested = others.find((r) => !r.is_system) ?? others[0]
      const answer = window.prompt(`${role.member_count} member(s) hold "${role.name}". Type the role that takes them:`, suggested?.slug ?? '')
      if (answer === null) return
      target = others.find((r) => r.slug === answer.trim() || r.name.toLowerCase() === answer.trim().toLowerCase())
      if (!target || target.id === role.id) return window.alert('No role by that name.')
    } else if (!window.confirm(`Delete the role "${role.name}"?`)) return
    deleteRole.mutate({ id: role.id, reassignTo: target?.id })
  }
  const submitNew = () => {
    const base = rows.find((r) => r.slug === copyFrom)
    createRole.mutate(
      { name: newName, description: newDescription, permissions: base && !base.is_system ? base.permissions : [] },
      {
        onSuccess: () => {
          setNewName('')
          setNewDescription('')
        },
      },
    )
  }

  return (
    <>
      <PageHeader
        title="Roles"
        count={`${rows.length} roles`}
        context={<span>{canEdit ? 'tick a box to grant it; changes apply to every member of the role at once' : 'what each role may do'}</span>}
      />
      <div className="space-y-4">
        <Panel testId="roles">
          <ErrorText error={patchRole.error ?? deleteRole.error} />
          <Table hover>
            <thead>
              <tr>
                <th rowSpan={2} className="align-bottom">
                  Role
                </th>
                <th rowSpan={2} className="align-bottom text-right">
                  Members
                </th>
                {groups.map(([group, codes]) => (
                  <th key={group} colSpan={codes.length} className="border-l border-line text-center">
                    {group}
                  </th>
                ))}
                {canEdit ? <th rowSpan={2} /> : null}
              </tr>
              <tr>
                {groups.flatMap(([, codes]) =>
                  codes.map((code, i) => (
                    <th key={code} className={clsx('text-center normal-case tracking-normal', i === 0 && 'border-l border-line')} title={catalog.get(code)?.description}>
                      {catalog.get(code)?.label ?? code}
                    </th>
                  )),
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((role) => {
                const editable = canEdit && !role.is_system
                return (
                  <tr key={role.id} data-testid={`roles.row.${role.slug}`}>
                    <td>
                      {renaming?.id === role.id ? (
                        <form
                          className="flex items-center gap-1"
                          onSubmit={(e) => {
                            e.preventDefault()
                            patchRole.mutate({ id: role.id, body: { name: renaming.name, reason: 'renamed' } }, { onSuccess: () => setRenaming(null) })
                          }}
                        >
                          <Input autoFocus className="w-36" value={renaming.name} onChange={(e) => setRenaming({ id: role.id, name: e.target.value })} data-testid={`roles.row.${role.slug}.name`} />
                          <Button type="submit" variant="primary" className="h-6 px-2">
                            Save
                          </Button>
                          <Button type="button" variant="ghost" className="h-6 px-2" onClick={() => setRenaming(null)}>
                            Cancel
                          </Button>
                        </form>
                      ) : (
                        <div>
                          <span className="font-medium">{role.name}</span> {role.is_system ? <Badge tone="accent">system</Badge> : null}
                          {role.description ? <div className="text-[11px] text-muted">{role.description}</div> : null}
                        </div>
                      )}
                    </td>
                    <td className="text-right">
                      <Mono testId={`roles.row.${role.slug}.members`}>{role.member_count}</Mono>
                    </td>
                    {groups.flatMap(([, codes]) =>
                      codes.map((code, i) => {
                        const on = role.is_system || role.permissions.includes(code)
                        return (
                          <td key={code} className={clsx('text-center', i === 0 && 'border-l border-line')}>
                            <Checkbox
                              checked={on}
                              disabled={!editable || patchRole.isPending}
                              onChange={(e) => toggle(role, code, e.target.checked)}
                              data-testid={`roles.row.${role.slug}.perm.${code}`}
                              title={catalog.get(code)?.description}
                            />
                          </td>
                        )
                      }),
                    )}
                    {canEdit ? (
                      <td className="whitespace-nowrap text-right">
                        {editable ? (
                          <>
                            <Button variant="ghost" className="h-6 px-2" onClick={() => setRenaming({ id: role.id, name: role.name })} data-testid={`roles.row.${role.slug}.rename`}>
                              Rename
                            </Button>
                            <Button variant="ghost" className="h-6 px-2 text-bad" onClick={() => remove(role)} data-testid={`roles.row.${role.slug}.delete`}>
                              Delete
                            </Button>
                          </>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                )
              })}
            </tbody>
          </Table>
        </Panel>
        {canEdit ? (
          <Panel title="New role" testId="roles.new">
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                if (newName.trim()) submitNew()
              }}
            >
              <Field label="Name">
                <Input data-testid="roles.new.name" className="w-40" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Scout" />
              </Field>
              <Field label="Description">
                <Input data-testid="roles.new.description" className="w-64" value={newDescription} onChange={(e) => setNewDescription(e.target.value)} placeholder="what this role is for" />
              </Field>
              <Field label="Start from">
                <Select data-testid="roles.new.copy" value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
                  <option value="">no permissions</option>
                  {rows
                    .filter((r) => !r.is_system)
                    .map((r) => (
                      <option key={r.id} value={r.slug}>
                        copy of {r.name}
                      </option>
                    ))}
                </Select>
              </Field>
              <Button data-testid="roles.new.create" type="submit" variant="primary" disabled={!newName.trim() || createRole.isPending}>
                Create
              </Button>
            </form>
            <ErrorText error={createRole.error} />
          </Panel>
        ) : null}
      </div>
    </>
  )
}
