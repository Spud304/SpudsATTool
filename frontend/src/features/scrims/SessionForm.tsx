import { useState } from 'react'
import { useOpponents, useRosterMutations, useScrimVocab } from '@/lib/api/hooks'
import type { SessionCreateIn, SessionOut } from '@/lib/api/client'
import { Button, ErrorText, Field, Input, Select, Textarea } from '@/components/ui'
import { fromLocalInput, toLocalInput } from './format'

type Draft = {
  title: string
  date: string
  kind: string
  opponent_id: string
  new_opponent: string
  stage_code: string
  system_name: string
  moveme_system: string
  motd: string
  default_our_side: string
}

function draftFrom(session?: SessionOut): Draft {
  return {
    title: session?.title ?? '',
    date: toLocalInput(session?.date) || defaultTonight(),
    kind: session?.kind ?? 'practice',
    opponent_id: session?.opponent_id ? String(session.opponent_id) : '',
    new_opponent: '',
    stage_code: session?.stage ?? '',
    system_name: session?.system_name ?? '',
    moveme_system: session?.moveme_system ?? '',
    motd: session?.motd ?? '',
    default_our_side: session?.default_our_side ?? '',
  }
}

/** 19:00 local today, the usual practice slot. */
function defaultTonight(): string {
  const d = new Date()
  d.setHours(19, 0, 0, 0)
  return toLocalInput(d.toISOString())
}

/** Shared by "New scrim" and the header's edit mode; the caller decides what to do with the payload. */
export function SessionForm({
  session,
  submitLabel,
  pending,
  error,
  testPrefix,
  onSubmit,
  onCancel,
}: {
  session?: SessionOut
  submitLabel: string
  pending: boolean
  error: unknown
  testPrefix: string
  onSubmit: (payload: SessionCreateIn) => void
  onCancel?: () => void
}) {
  const vocab = useScrimVocab()
  const opponents = useOpponents()
  const { createOpponent } = useRosterMutations()
  const [d, setD] = useState<Draft>(() => draftFrom(session))
  const set = <K extends keyof Draft>(key: K) => (value: Draft[K]) => setD((prev) => ({ ...prev, [key]: value }))

  const submit = async () => {
    let opponentId: number | null = d.opponent_id ? Number(d.opponent_id) : null
    if (d.opponent_id === 'new' && d.new_opponent.trim()) {
      const created = await createOpponent.mutateAsync({ name: d.new_opponent.trim(), notes: '', alliance_id: null })
      opponentId = created.id
    } else if (d.opponent_id === 'new') {
      opponentId = null
    }
    onSubmit({
      title: d.title.trim(),
      date: fromLocalInput(d.date),
      kind: d.kind,
      opponent_id: opponentId,
      stage_code: d.stage_code || null,
      system_name: d.system_name.trim(),
      moveme_system: d.moveme_system.trim(),
      motd: d.motd,
      default_our_side: d.default_our_side,
    })
  }
  const valid = d.title.trim().length > 0 && d.date.length > 0

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) void submit()
      }}
    >
      <Field label="Title">
        <Input data-testid={`${testPrefix}.title`} value={d.title} onChange={(e) => set('title')(e.target.value)} placeholder="OF 99" />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="When">
          <Input data-testid={`${testPrefix}.date`} type="datetime-local" value={d.date} onChange={(e) => set('date')(e.target.value)} />
        </Field>
        <Field label="Kind">
          <Select data-testid={`${testPrefix}.kind`} value={d.kind} onChange={(e) => set('kind')(e.target.value)}>
            {(vocab.data?.kinds ?? [d.kind]).map((k) => (
              <option key={k} value={k}>
                {k.replace('_', ' ')}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Opponent">
        <Select data-testid={`${testPrefix}.opponent`} value={d.opponent_id} onChange={(e) => set('opponent_id')(e.target.value)}>
          <option value="">none yet</option>
          {(opponents.data ?? [])
            .filter((o) => o.is_active || String(o.id) === d.opponent_id)
            .map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          <option value="new">new opponent…</option>
        </Select>
      </Field>
      {d.opponent_id === 'new' ? (
        <Field label="New opponent name">
          <Input data-testid={`${testPrefix}.opponent.new`} value={d.new_opponent} onChange={(e) => set('new_opponent')(e.target.value)} />
        </Field>
      ) : null}
      <div className="grid grid-cols-2 gap-2">
        <Field label="Stage">
          <Select data-testid={`${testPrefix}.stage`} value={d.stage_code} onChange={(e) => set('stage_code')(e.target.value)}>
            <option value="">unset</option>
            {(vocab.data?.stages ?? []).map((s) => (
              <option key={s.code} value={s.code}>
                {s.label} (bo{s.best_of}, {s.bans_per_side} bans)
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Our side">
          <Select data-testid={`${testPrefix}.side`} value={d.default_our_side} onChange={(e) => set('default_our_side')(e.target.value)}>
            <option value="">decide per set</option>
            {(vocab.data?.sides ?? ['A', 'B']).map((s) => (
              <option key={s} value={s}>
                Team {s}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="System">
          <Input data-testid={`${testPrefix}.system`} value={d.system_name} onChange={(e) => set('system_name')(e.target.value)} />
        </Field>
        <Field label="Move-me system">
          <Input data-testid={`${testPrefix}.moveme`} value={d.moveme_system} onChange={(e) => set('moveme_system')(e.target.value)} />
        </Field>
      </div>
      <Field label="MotD">
        <Textarea data-testid={`${testPrefix}.motd`} rows={3} className="w-full" value={d.motd} onChange={(e) => set('motd')(e.target.value)} />
      </Field>
      <div className="flex items-center gap-2">
        <Button data-testid={`${testPrefix}.submit`} type="submit" variant="primary" disabled={!valid || pending || createOpponent.isPending}>
          {submitLabel}
        </Button>
        {onCancel ? (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
      <ErrorText error={error ?? createOpponent.error} testId={`${testPrefix}.error`} />
    </form>
  )
}
