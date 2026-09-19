import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useShareLinks, useShareMutations } from '@/lib/api/hooks'
import { Badge, Button, ErrorText, Input, Mono } from '@/components/ui'
import { whenAt } from './format'

/** Captain-side share links: make one, copy it, revoke it. Anyone with the URL sees the board read-only. */
export function SharePanel({ scrimId, onClose }: { scrimId: number; onClose: () => void }) {
  const links = useShareLinks(scrimId)
  const { createShare, revokeShare } = useShareMutations(scrimId)
  const [days, setDays] = useState(7)
  const [copied, setCopied] = useState<number | null>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const copy = async (id: number, url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(id)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      window.prompt('Copy the link:', url)
    }
  }
  return createPortal(
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onMouseDown={onClose} data-testid="scrim.share">
      <aside className="flex h-full w-[460px] flex-col gap-3 overflow-y-auto border-l border-line bg-panel p-3 text-body shadow-lg" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-body font-semibold uppercase tracking-wide text-muted">Share links</h2>
          <Button variant="ghost" className="h-6 px-1.5" onClick={onClose} data-testid="scrim.share.close">
            close
          </Button>
        </div>
        <p className="text-muted">Anyone with a link sees this scrim read-only, live, without fit text. Links stop working when they expire, when you revoke them, or when the scrim is archived.</p>
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            createShare.mutate({ days })
          }}
        >
          <label className="flex flex-col gap-0.5 text-[11px] text-muted">
            valid for (days)
            <Input data-testid="scrim.share.days" type="number" min={1} max={90} className="w-20" value={days} onChange={(e) => setDays(Number(e.target.value))} />
          </label>
          <Button type="submit" variant="primary" disabled={createShare.isPending || days < 1 || days > 90} data-testid="scrim.share.create">
            New link
          </Button>
        </form>
        <ErrorText error={createShare.error ?? revokeShare.error ?? links.error} />
        <ul className="space-y-2">
          {(links.data ?? []).map((l) => (
            <li key={l.id} className="rounded border border-line p-2" data-testid={`scrim.share.link.${l.id}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <Badge tone={l.is_live ? 'ok' : 'muted'}>{l.is_live ? 'live' : l.revoked_at ? 'revoked' : 'expired'}</Badge>
                  <span className="text-muted">
                    by {l.created_by_name || 'unknown'} {whenAt(l.created_at)} · until {whenAt(l.expires_at)}
                  </span>
                </span>
                <span className="flex gap-1">
                  {l.is_live ? (
                    <>
                      <Button className="h-6 px-2" onClick={() => copy(l.id, l.url)} data-testid={`scrim.share.link.${l.id}.copy`}>
                        {copied === l.id ? 'Copied' : 'Copy'}
                      </Button>
                      <Button variant="danger" className="h-6 px-2" disabled={revokeShare.isPending} onClick={() => revokeShare.mutate({ linkId: l.id })} data-testid={`scrim.share.link.${l.id}.revoke`}>
                        Revoke
                      </Button>
                    </>
                  ) : null}
                </span>
              </div>
              {l.is_live ? (
                <Mono className="mt-1 block truncate text-[11px] text-muted" testId={`scrim.share.link.${l.id}.url`}>
                  {l.url}
                </Mono>
              ) : null}
            </li>
          ))}
          {links.data && links.data.length === 0 ? <li className="text-muted">No links yet.</li> : null}
        </ul>
      </aside>
    </div>,
    document.body,
  )
}
