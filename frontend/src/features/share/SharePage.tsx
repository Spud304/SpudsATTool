import { useParams } from '@tanstack/react-router'
import { useSharedScrim } from '@/lib/api/hooks'
import { Empty, ErrorText, Panel } from '@/components/ui'
import { Board } from '@/features/scrims/ScrimPage'
import type { Perms } from '@/features/scrims/shared'
import { useScrimStream } from '@/features/scrims/useScrimStream'
import { keys } from '@/lib/api/hooks'

const NOBODY: Perms = { edit: false, manage: false, score: false, userId: null }

/** The board for whoever holds a share link: read-only, live, fit text hidden. No login involved. */
export function SharePage() {
  const { token } = useParams({ from: '/share/$token' })
  const scrim = useSharedScrim(token)
  const stream = useScrimStream(scrim.data?.id ?? 0, Boolean(scrim.data), {
    url: `/api/share/${token}/events`,
    queryKey: keys.share(token),
    presence: false,
  })
  if (scrim.error)
    return (
      <Panel title="Shared scrim">
        <Empty>This link is not valid any more. Ask whoever sent it for a new one.</Empty>
        <ErrorText error={null} />
      </Panel>
    )
  if (!scrim.data) return <Empty>Loading…</Empty>
  return <Board scrim={scrim.data} perms={NOBODY} stream={stream} shared />
}
