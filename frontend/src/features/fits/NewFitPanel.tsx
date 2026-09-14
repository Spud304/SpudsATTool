import { useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useFitMutations, useMe } from '@/lib/api/hooks'
import type { ParseOut } from '@/lib/api/client'
import { Badge, Button, ErrorText, Field, Input, Mono, Panel, Select, Textarea } from '@/components/ui'
import { FIT_STATUSES, num } from './format'

/** Paste an EFT block (and optionally the Pyfa stats block); the server previews what it understood. */
export function NewFitPanel() {
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_library)
  const navigate = useNavigate()
  const { parseFit, createFit } = useFitMutations()
  const parse = parseFit.mutateAsync
  const [eft, setEft] = useState('')
  const [pyfa, setPyfa] = useState('')
  const [name, setName] = useState('')
  const [status, setStatus] = useState<string>('suggested')
  const [preview, setPreview] = useState<ParseOut | null>(null)

  useEffect(() => {
    if (!eft.trim()) {
      setPreview(null)
      return
    }
    const handle = setTimeout(() => {
      parse({ eft_text: eft, pyfa_summary: pyfa })
        .then(setPreview)
        .catch(() => setPreview(null))
    }, 300)
    return () => clearTimeout(handle)
  }, [eft, pyfa, parse])

  const submit = async () => {
    const fit = await createFit.mutateAsync({
      eft_text: eft,
      name: name.trim() || null,
      pyfa_summary: pyfa,
      status: canManage ? status : null,
    })
    setEft('')
    setPyfa('')
    setName('')
    setPreview(null)
    await navigate({ to: '/fits/$fitId', params: { fitId: String(fit.id) } })
  }

  return (
    <Panel title="New fit from clipboard" testId="fits.new">
      <div className="space-y-2">
        <Field label="EFT text">
          <Textarea data-testid="fits.new.eft" rows={12} placeholder={'[Hull, Fit name]\nModule, Charge\n…'} value={eft} onChange={(e) => setEft(e.target.value)} />
        </Field>
        <Field label="Pyfa stats block (optional)">
          <Textarea data-testid="fits.new.pyfa" rows={5} placeholder={'DPS: …\nEHP: …\nSpeed: … m/s'} value={pyfa} onChange={(e) => setPyfa(e.target.value)} />
        </Field>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Fit name">
            <Input data-testid="fits.new.name" className="w-56" placeholder={preview?.fit_name || 'from header'} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          {canManage ? (
            <Field label="Status">
              <Select data-testid="fits.new.status" value={status} onChange={(e) => setStatus(e.target.value)}>
                {FIT_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <span className="pb-1 text-[11px] text-muted">Lands as suggested until a theorycrafter activates it.</span>
          )}
          <Button data-testid="fits.new.save" variant="primary" disabled={!preview?.ok || createFit.isPending} onClick={submit}>
            Save fit
          </Button>
        </div>
        <ErrorText error={createFit.error} testId="fits.new.error" />
        {preview ? <PreviewBlock preview={preview} /> : null}
      </div>
    </Panel>
  )
}

function PreviewBlock({ preview }: { preview: ParseOut }) {
  const stats = preview.stats
  return (
    <div className="space-y-1 border-t border-line pt-2 text-[12px]" data-testid="fits.new.preview">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={preview.hull_type_id ? 'ok' : 'bad'}>{preview.hull_name || 'no hull'}</Badge>
        <span>{preview.fit_name}</span>
        <Mono className="text-muted">{preview.items.length} lines</Mono>
        {preview.has_links ? <Badge tone="accent">links</Badge> : null}
        {stats.ok ? (
          <Mono className="text-muted">
            {num(stats.dps)} dps · {num(stats.ehp_k, 1)}k ehp · {num(stats.speed_ms)} m/s
          </Mono>
        ) : null}
      </div>
      {preview.errors.map((e) => (
        <p key={e} className="text-bad">
          {e}
        </p>
      ))}
      {preview.unresolved.length ? (
        <p className="text-warn">
          Unknown items: <Mono>{preview.unresolved.join(', ')}</Mono>
        </p>
      ) : null}
      {preview.warnings.map((w) => (
        <p key={w} className="text-muted">
          {w}
        </p>
      ))}
    </div>
  )
}
