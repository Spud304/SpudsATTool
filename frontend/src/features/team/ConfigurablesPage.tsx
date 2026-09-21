import { useState } from 'react'
import { useCompMutations, useCompVocab, useMe, useOpponents, useRosterMutations, useWarpLabelMutations, useWarpLabels } from '@/lib/api/hooks'
import type { ArchetypeOut, OpponentOut, WarpLabelOut } from '@/lib/api/client'
import { Badge, Button, Checkbox, Empty, ErrorText, Field, Input, Mono, PageHeader, Panel, Table } from '@/components/ui'
import { usePageTitle } from '@/hooks/usePageTitle'

/** The sheet's Configurables tab: opponents, comp archetypes and warp-in labels, each behind its own permission. */
export function ConfigurablesPage() {
  usePageTitle('Configurables')
  const me = useMe()
  const caps = me.data?.capabilities
  const panels = [caps?.manage_scrims, caps?.manage_library, caps?.manage_team].filter(Boolean).length
  return (
    <>
      <PageHeader title="Configurables" context={<span>the lists the scrim and comp pages pick from</span>} />
      {panels === 0 ? (
        <Empty hint="Opponents need Manage scrims, archetypes Manage library, warp-in labels Manage team.">Nothing here for your role.</Empty>
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          {caps?.manage_scrims ? <OpponentsPanel canManage /> : null}
          {caps?.manage_library ? <ArchetypesPanel /> : null}
          {caps?.manage_team ? <WarpLabelsPanel /> : null}
        </div>
      )}
    </>
  )
}

export function OpponentsPanel({ canManage }: { canManage: boolean }) {
  const opponents = useOpponents()
  const { createOpponent, patchOpponent } = useRosterMutations()
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  return (
    <Panel title={`Opponents${opponents.data ? ` (${opponents.data.length})` : ''}`} testId="opponents">
      <ErrorText error={patchOpponent.error} />
      {opponents.data?.length ? (
        <Table hover>
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
        <Empty hint="Opponents are picked when a scrim is scheduled.">No opponents yet.</Empty>
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
      <td>
        {canManage ? (
          <Checkbox data-testid={`${id}.active`} checked={opponent.is_active} onChange={(e) => onPatch({ is_active: e.target.checked })} />
        ) : (
          <Badge tone={opponent.is_active ? 'ok' : 'muted'}>{opponent.is_active ? 'active' : 'inactive'}</Badge>
        )}
      </td>
    </tr>
  )
}

/** Comp archetypes: retire the ones that are in use, delete the ones that never got used. */
function ArchetypesPanel() {
  const vocab = useCompVocab()
  const { createArchetype, patchArchetype, deleteArchetype } = useCompMutations()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const rows = [...(vocab.data?.archetypes ?? [])].sort((a, b) => Number(a.is_retired) - Number(b.is_retired) || a.name.localeCompare(b.name))
  return (
    <Panel title={`Archetypes${vocab.data ? ` (${rows.length})` : ''}`} testId="config.archetypes">
      <ErrorText error={patchArchetype.error ?? deleteArchetype.error} />
      {rows.length ? (
        <Table hover>
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th className="text-right">Used</th>
              <th>Retired</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <ArchetypeRow
                key={a.id}
                archetype={a}
                onPatch={(body) => patchArchetype.mutate({ id: a.id, body })}
                onDelete={() => window.confirm(`Delete the archetype "${a.name}"?`) && deleteArchetype.mutate(a.id)}
              />
            ))}
          </tbody>
        </Table>
      ) : (
        <Empty>No archetypes yet.</Empty>
      )}
      <form
        className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3"
        onSubmit={(e) => {
          e.preventDefault()
          createArchetype.mutate(
            { name: name.trim(), description: description.trim(), sort_order: 0 },
            {
              onSuccess: () => {
                setName('')
                setDescription('')
              },
            },
          )
        }}
      >
        <Field label="New archetype">
          <Input data-testid="config.archetypes.new.name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Description">
          <Input data-testid="config.archetypes.new.description" className="w-56" value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Button data-testid="config.archetypes.new.create" type="submit" variant="primary" disabled={!name.trim() || createArchetype.isPending}>
          Add archetype
        </Button>
        <ErrorText error={createArchetype.error} />
      </form>
    </Panel>
  )
}

function ArchetypeRow({ archetype: a, onPatch, onDelete }: { archetype: ArchetypeOut; onPatch: (body: { name?: string; description?: string; is_retired?: boolean }) => void; onDelete: () => void }) {
  const [name, setName] = useState(a.name)
  const [description, setDescription] = useState(a.description)
  const id = `config.archetypes.row.${a.id}`
  return (
    <tr data-testid={id} className={a.is_retired ? 'text-muted' : undefined}>
      <td>
        <Input data-testid={`${id}.name`} className="w-40" value={name} onChange={(e) => setName(e.target.value)} onBlur={() => name.trim() && name !== a.name && onPatch({ name })} />
      </td>
      <td>
        <Input
          data-testid={`${id}.description`}
          className="w-full"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          onBlur={() => description !== a.description && onPatch({ description })}
        />
      </td>
      <td className="text-right">
        <Mono>{a.in_use}</Mono>
      </td>
      <td>
        <Checkbox data-testid={`${id}.retired`} checked={a.is_retired} onChange={(e) => onPatch({ is_retired: e.target.checked })} />
      </td>
      <td className="whitespace-nowrap text-right">
        {a.in_use === 0 ? (
          <Button variant="ghost" className="h-6 px-2 text-bad" onClick={onDelete} data-testid={`${id}.delete`}>
            Delete
          </Button>
        ) : null}
      </td>
    </tr>
  )
}

/** Warp-in labels: the sheet's 48 configurables the set header's four warp calls pick from. */
function WarpLabelsPanel() {
  const labels = useWarpLabels()
  const { createLabel, patchLabel, deleteLabel } = useWarpLabelMutations()
  const [label, setLabel] = useState('')
  const rows = labels.data ?? []
  return (
    <Panel title={`Warp-in labels${labels.data ? ` (${rows.length})` : ''}`} testId="config.warp">
      <ErrorText error={patchLabel.error ?? deleteLabel.error} />
      {rows.length ? (
        <Table hover className="max-h-[60vh] overflow-y-auto">
          <thead>
            <tr>
              <th>Label</th>
              <th className="text-right">Used</th>
              <th>Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <WarpLabelRow
                key={r.id}
                row={r}
                onPatch={(body) => patchLabel.mutate({ id: r.id, body })}
                onDelete={() => window.confirm(`Delete the label "${r.label}"?`) && deleteLabel.mutate(r.id)}
              />
            ))}
          </tbody>
        </Table>
      ) : (
        <Empty>No labels yet.</Empty>
      )}
      <form
        className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3"
        onSubmit={(e) => {
          e.preventDefault()
          createLabel.mutate({ label: label.trim(), sort_order: 0 }, { onSuccess: () => setLabel('') })
        }}
      >
        <Field label="New label">
          <Input data-testid="config.warp.new.label" value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <Button data-testid="config.warp.new.create" type="submit" variant="primary" disabled={!label.trim() || createLabel.isPending}>
          Add label
        </Button>
        <ErrorText error={createLabel.error} />
      </form>
    </Panel>
  )
}

function WarpLabelRow({ row: r, onPatch, onDelete }: { row: WarpLabelOut; onPatch: (body: { label?: string; is_active?: boolean }) => void; onDelete: () => void }) {
  const [label, setLabel] = useState(r.label)
  const id = `config.warp.row.${r.id}`
  return (
    <tr data-testid={id} className={r.is_active ? undefined : 'text-muted'}>
      <td>
        <Input data-testid={`${id}.label`} className="w-40" value={label} onChange={(e) => setLabel(e.target.value)} onBlur={() => label.trim() && label !== r.label && onPatch({ label })} />
      </td>
      <td className="text-right">
        <Mono>{r.in_use}</Mono>
      </td>
      <td>
        <Checkbox data-testid={`${id}.active`} checked={r.is_active} onChange={(e) => onPatch({ is_active: e.target.checked })} />
      </td>
      <td className="whitespace-nowrap text-right">
        {r.in_use === 0 ? (
          <Button variant="ghost" className="h-6 px-2 text-bad" onClick={onDelete} data-testid={`${id}.delete`}>
            Delete
          </Button>
        ) : null}
      </td>
    </tr>
  )
}
