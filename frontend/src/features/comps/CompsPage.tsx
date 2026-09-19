import { useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useCompMutations, useComps, useCompVocab, useMe } from '@/lib/api/hooks'
import { Badge, Button, Empty, ErrorText, Field, Input, Mono, Panel, Select, Table } from '@/components/ui'
import { num, when } from '@/features/fits/format'
import { COMP_STATUSES, capTone, compStatusTone } from './format'
import { usePageTitle } from '@/hooks/usePageTitle'
import { useSlashFocus } from '@/hooks/useSlashFocus'

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: 'active,construction', label: 'Active + construction' },
  { value: 'active', label: 'Active' },
  { value: 'construction', label: 'Construction' },
  { value: 'suggested', label: 'Suggested' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'retired', label: 'Retired' },
  { value: '', label: 'All' },
]

export function CompsPage() {
  usePageTitle('Comps')
  useSlashFocus('comps.search')
  const me = useMe()
  const active = me.data?.team?.active_ruleset ?? ''
  const vocab = useCompVocab()

  const [status, setStatus] = useState('active,construction')
  const [archetype, setArchetype] = useState('')
  const [q, setQ] = useState('')
  const comps = useComps(
    {
      status: status || undefined,
      archetype: archetype ? Number(archetype) : undefined,
      q: q.trim() || undefined,
    },
    Boolean(active),
  )

  if (me.data && !active) return <Empty>No ruleset imported yet.</Empty>

  return (
    <div className="grid gap-4 xl:grid-cols-[3fr_1fr]">
      <Panel
        title={`Comps · ${active}${comps.data ? ` (${comps.data.length})` : ''}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Input data-testid="comps.search" placeholder="search comp or hull" className="w-48" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select data-testid="comps.status" value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_FILTERS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
            <Select value={archetype} onChange={(e) => setArchetype(e.target.value)}>
              <option value="">any archetype</option>
              {(vocab.data?.archetypes ?? [])
                .filter((a) => !a.is_retired)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </Select>
          </div>
        }
      >
        <ErrorText error={comps.error} />
        {comps.data?.length ? (
          <Table>
            <thead>
              <tr>
                <th>Comp</th>
                <th>Status</th>
                <th>Archetype</th>
                <th className="text-right">Points</th>
                <th>Legal</th>
                <th>Hulls</th>
                <th className="text-right">DPS</th>
                <th className="text-right">EHP k</th>
                <th className="text-right">Min m/s</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {comps.data.map((c) => {
                const ev = c.evaluation
                return (
                  <tr key={c.id} data-testid={`comps.row.${c.id}`}>
                    <td>
                      <Link to="/comps/$compId" params={{ compId: String(c.id) }} className="text-accent hover:underline">
                        {c.name}
                      </Link>
                    </td>
                    <td>
                      <Badge tone={compStatusTone(c.status)}>{c.status}</Badge>
                    </td>
                    <td className="text-muted">{c.archetype ?? ''}</td>
                    <td className="text-right">
                      {ev ? (
                        <Mono className={ev.cap_status === 'OVER' ? 'text-bad' : ev.cap_status === 'UNDER' ? 'text-warn' : ''}>
                          {ev.total_points}/{ev.point_cap}
                        </Mono>
                      ) : (
                        <Mono className="text-muted">no table</Mono>
                      )}
                    </td>
                    <td>{ev ? <Badge tone={ev.is_legal ? 'ok' : 'bad'}>{ev.is_legal ? 'legal' : `${ev.error_count} err`}</Badge> : null}</td>
                    <td className="max-w-md text-[11px] text-muted">{c.hulls.filter(Boolean).join(', ')}</td>
                    <td className="text-right">
                      <Mono>{num(c.stats.dps_total)}</Mono>
                    </td>
                    <td className="text-right">
                      <Mono>{num(c.stats.ehp_k_total, 1)}</Mono>
                    </td>
                    <td className="text-right">
                      <Mono>{num(c.stats.speed_min)}</Mono>
                    </td>
                    <td className="text-muted">{when(c.updated_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </Table>
        ) : comps.isLoading ? (
          <Empty>Loading…</Empty>
        ) : (
          <Empty
            testId="comps.empty"
            hint={status !== 'active,construction' || archetype || q ? undefined : 'Create one with the panel on the right, or build in the scratchpad first.'}
            action={
              status !== 'active,construction' || archetype || q ? (
                <Button
                  data-testid="comps.clear"
                  onClick={() => {
                    setStatus('active,construction')
                    setArchetype('')
                    setQ('')
                  }}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          >
            No comps match these filters.
          </Empty>
        )}
      </Panel>
      <NewCompPanel />
    </div>
  )
}

function NewCompPanel() {
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_library)
  const navigate = useNavigate()
  const { createComp } = useCompMutations()
  const [name, setName] = useState('')
  const [status, setStatus] = useState<string>('construction')
  const submit = async () => {
    const comp = await createComp.mutateAsync({ name, status: canManage ? status : null, notes: '', ban_theory: '' })
    setName('')
    await navigate({ to: '/comps/$compId', params: { compId: String(comp.id) } })
  }
  return (
    <Panel title="New comp" testId="comps.new">
      <div className="space-y-2">
        <Field label="Name">
          <Input data-testid="comps.new.name" value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && name.trim() && submit()} />
        </Field>
        {canManage ? (
          <Field label="Status">
            <Select data-testid="comps.new.status" value={status} onChange={(e) => setStatus(e.target.value)}>
              {COMP_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
        ) : (
          <p className="text-[11px] text-muted">Lands as suggested until a theorycrafter promotes it.</p>
        )}
        <Button data-testid="comps.new.create" variant="primary" disabled={!name.trim() || createComp.isPending} onClick={submit}>
          Create and open builder
        </Button>
        <ErrorText error={createComp.error} />
        <p className="text-[11px] text-muted">
          Points shown are <Badge tone={capTone('EXACT')}>exact</Badge> when the comp spends the whole cap.
        </p>
      </div>
    </Panel>
  )
}
