import { useEffect } from 'react'
import { useMe } from '@/lib/api/hooks'

const FALLBACK = 'AT Tool'

/** Browser tab reads "Comps · <team>"; the team name comes from the session once it is known. */
export function usePageTitle(title: string | undefined) {
  const me = useMe()
  const team = me.data?.team?.name
  useEffect(() => {
    document.title = title ? `${title} · ${team ?? FALLBACK}` : (team ?? FALLBACK)
    return () => {
      document.title = FALLBACK
    }
  }, [title, team])
}
