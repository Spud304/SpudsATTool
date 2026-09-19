import { useEffect, useState } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import { useFit, useFitLegality, useFitMutations, useMe } from '@/lib/api/hooks'
import type { FitOut } from '@/lib/api/client'
import { Badge, Button, Checkbox, Empty, ErrorText, Field, Input, Mono, Panel, Select, Table, Textarea } from '@/components/ui'
import { FIT_STATUSES, num, severityTone, statusTone, when } from './format'
import { usePageTitle } from '@/hooks/usePageTitle'

export function FitDetailPage() {
  usePageTitle('Fit')
  const { fitId } = useParams({ strict: false }) as { fitId?: string }
  const id = Number(fitId)
  const fit = useFit(id)
  if (fit.isLoading) return <Empty>Loading…</Empty>
  if (fit.error) return <ErrorText error={fit.error} />
  if (!fit.data) return <Empty>Not found.</Empty>
  const f = fit.data
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/fits" className="text-muted hover:underline">
          Fits
        </Link>
        <span className="text-muted">/</span>
        <span className="font-semibold">{f.ship_name}</span>
        <span>{f.name}</span>
        <Badge tone={statusTone(f.status)} testId="fit.status.badge">
          {f.status}
        </Badge>
        {f.has_links ? <Badge tone="accent">links</Badge> : null}
        <span className="text-[11px] text-muted">
          {f.created_by_name ? `by ${f.created_by_name}, ` : ''}created {when(f.created_at)}
          {f.reviewed_by_name ? `, reviewed by ${f.reviewed_by_name} ${when(f.reviewed_at)}` : ''}
        </span>
      </div>
      <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
        <Editor key={f.updated_at} fit={f} />
        <div className="space-y-4">
          <StatsPanel fit={f} />
          <StatusPanel fit={f} />
          <LegalityPanel fit={f} />
        </div>
      </div>
    </div>
  )
}

function Editor({ fit }: { fit: FitOut }) {
  const { patchFit } = useFitMutations()
  const [name, setName] = useState(fit.name)
  const [eft, setEft] = useState(fit.eft_text)
  const [pyfa, setPyfa] = useState(fit.pyfa_summary)
  const [copied, setCopied] = useState(false)
  const dirty = name !== fit.name || eft !== fit.eft_text || pyfa !== fit.pyfa_summary
  const copy = async () => {
    await navigator.clipboard.writeText(fit.eft_text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <Panel
      title="Fit"
      actions={
        <div className="flex items-center gap-2">
          <Button data-testid="fit.copy" onClick={copy}>
            {copied ? 'Copied' : 'Copy EFT'}
          </Button>
          {fit.can_edit ? (
            <Button
              data-testid="fit.save"
              variant="primary"
              disabled={!dirty || patchFit.isPending}
              onClick={() => patchFit.mutate({ id: fit.id, body: { name, eft_text: eft, pyfa_summary: pyfa, reason: '' } })}
            >
              Save
            </Button>
          ) : null}
        </div>
      }
    >
      <div className="space-y-2">
        <ErrorText error={patchFit.error} />
        {fit.can_edit ? (
          <Field label="Fit name">
            <Input data-testid="fit.name" className="w-72" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        ) : null}
        <Field label="EFT text">
          <Textarea data-testid="fit.eft" rows={Math.min(40, Math.max(12, eft.split('\n').length + 1))} value={eft} readOnly={!fit.can_edit} onChange={(e) => setEft(e.target.value)} />
        </Field>
        <Field label="Pyfa stats block">
          <Textarea data-testid="fit.pyfa" rows={6} value={pyfa} readOnly={!fit.can_edit} placeholder="paste the Pyfa stats block to fill the numbers" onChange={(e) => setPyfa(e.target.value)} />
        </Field>
        {fit.unresolved_names.length ? (
          <p className="text-warn" data-testid="fit.unknown">
            Unknown items: <Mono>{fit.unresolved_names.join(', ')}</Mono>
          </p>
        ) : null}
      </div>
    </Panel>
  )
}

function StatsPanel({ fit }: { fit: FitOut }) {
  const rows: [string, string][] = [
    ['DPS', num(fit.dps)],
    ['Volley', num(fit.volley)],
    ['EHP', fit.ehp_k == null ? '' : `${num(fit.ehp_k, 1)}k`],
    ['Speed', fit.speed_ms == null ? '' : `${num(fit.speed_ms)} m/s`],
    ['Signature', fit.sig_radius_m == null ? '' : `${num(fit.sig_radius_m)} m`],
    ['Capacitor', fit.cap_stable_pct != null ? `stable ${num(fit.cap_stable_pct)}%` : fit.cap_lasts_s != null ? `lasts ${fit.cap_lasts_s}s` : ''],
    ['Targeting', fit.targeting_range_km == null ? '' : `${num(fit.targeting_range_km, 1)} km`],
  ]
  return (
    <Panel title="Stats" actions={fit.stats_parse_ok ? <Badge tone="ok">parsed</Badge> : <Badge tone="muted">no Pyfa block</Badge>}>
      <Table>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td className="text-muted">{label}</td>
              <td className="text-right">
                <Mono>{value}</Mono>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Panel>
  )
}

function StatusPanel({ fit }: { fit: FitOut }) {
  const me = useMe()
  const { patchFit } = useFitMutations()
  const [status, setStatus] = useState(fit.status)
  const [reason, setReason] = useState('')
  useEffect(() => setStatus(fit.status), [fit.status])
  if (!me.data?.capabilities?.manage_library) return null
  return (
    <Panel title="Status" testId="fit.status">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Status">
          <Select data-testid="fit.status.select" value={status} onChange={(e) => setStatus(e.target.value)}>
            {FIT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Reason">
          <Input data-testid="fit.status.reason" className="w-64" value={reason} placeholder="why (goes to the audit log)" onChange={(e) => setReason(e.target.value)} />
        </Field>
        <Button
          data-testid="fit.status.apply"
          variant="primary"
          disabled={status === fit.status || patchFit.isPending}
          onClick={() => {
            patchFit.mutate({ id: fit.id, body: { status, reason } })
            setReason('')
          }}
        >
          Apply
        </Button>
      </div>
      <ErrorText error={patchFit.error} />
    </Panel>
  )
}

function LegalityPanel({ fit }: { fit: FitOut }) {
  const me = useMe()
  const active = me.data?.team?.active_ruleset ?? undefined
  const [flagship, setFlagship] = useState(false)
  const legality = useFitLegality(fit.id, active, flagship)
  const result = legality.data
  return (
    <Panel
      title="Module legality"
      actions={
        <div className="flex items-center gap-2">
          <Mono className="text-muted">{active ?? 'no ruleset'}</Mono>
          <label className="flex items-center gap-1 text-[11px] text-muted">
            <Checkbox checked={flagship} onChange={(e) => setFlagship(e.target.checked)} /> flagship
          </label>
        </div>
      }
    >
      <ErrorText error={legality.error} />
      {result ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Badge tone={result.is_legal ? 'ok' : 'bad'} testId="fit.legality.verdict">
              {result.is_legal ? 'legal' : 'illegal'}
            </Badge>
            <Mono className="text-muted">
              {result.item_count} items checked · rev {result.revision}
            </Mono>
          </div>
          {result.violations.length ? (
            <ul className="space-y-1 text-[12px]">
              {result.violations.map((v, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-1">
                  <Badge tone={severityTone(v.severity)}>{v.code}</Badge>
                  <span>{v.message}</span>
                  {v.line_nos.length ? <Mono className="text-muted">line {v.line_nos.join(', ')}</Mono> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No module rule violations.</p>
          )}
        </div>
      ) : legality.isLoading ? (
        <Empty>Checking…</Empty>
      ) : (
        <Empty>No ruleset imported.</Empty>
      )}
    </Panel>
  )
}
