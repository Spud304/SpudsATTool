import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { SessionOut, SetDoc, ViewerOut } from '@/lib/api/client'
import { keys, leavePresence, sendPresence, upsertSet } from '@/lib/api/hooks'

export type StreamStatus = 'connecting' | 'live' | 'offline'

const HEARTBEAT_MS = 15_000
const WATCHDOG_MS = 45_000 // the server pings every 20 s

type Message = { seq: number | null; kind: string; payload: Record<string, unknown> }

/**
 * One EventSource per open scrim page. Set events replace whole set documents in the query cache;
 * header and attendance events refetch the session; presence arrives as the viewer list.
 * Also owns the presence heartbeat: call `setFocus` from fields so others see where you are.
 */
export type StreamOptions = { url?: string; queryKey?: readonly unknown[]; presence?: boolean }

export function useScrimStream(sessionId: number, enabled: boolean, options: StreamOptions = {}) {
  const { url = `/api/scrims/${sessionId}/events`, queryKey, presence = true } = options
  const keyString = JSON.stringify(queryKey ?? keys.scrim(sessionId)) // a stable dependency; callers pass fresh arrays
  const qc = useQueryClient()
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const [viewers, setViewers] = useState<ViewerOut[]>([])
  const focusRef = useRef<string | null>(null)
  const focusTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (!enabled) return
    let lastFrame = Date.now()
    const key = JSON.parse(keyString) as readonly unknown[]
    const refetch = () => void qc.invalidateQueries({ queryKey: key })
    // Start after the document we already hold: without `since` the server replays every stored
    // change from the beginning and the page visibly re-applies them. Reconnects send Last-Event-ID.
    const since = qc.getQueryData<SessionOut>(key)?.event_seq ?? 0
    const source = new EventSource(`${url}?since=${since}`)
    const alive = () => {
      lastFrame = Date.now()
      setStatus('live')
    }
    const on = (kind: string, handler: (msg: Message) => void) =>
      source.addEventListener(kind, (event) => {
        alive()
        const msg = JSON.parse((event as MessageEvent).data) as Message
        handler(msg)
        // After the handler: upsertSet compares a new set against the position before this event.
        const seq = msg.seq
        if (seq != null) qc.setQueryData<SessionOut>(key, (old) => (old && seq > old.event_seq ? { ...old, event_seq: seq } : old))
      })
    source.onopen = alive
    source.onerror = () => setStatus('offline')
    on('ping', () => undefined)
    on('set', (msg) => {
      const doc = msg.payload.set as SetDoc
      qc.setQueryData<SessionOut>(key, (old) => (old ? upsertSet(old, doc) : old))
    })
    on('set_deleted', (msg) => {
      const id = msg.payload.set_id as number
      qc.setQueryData<SessionOut>(key, (old) => (old ? { ...old, sets: old.sets.filter((s) => s.id !== id) } : old))
    })
    on('session', refetch)
    on('attendance', refetch)
    on('resync', refetch)
    on('presence', (msg) => setViewers((msg.payload.viewers as ViewerOut[]) ?? []))

    const watchdog = window.setInterval(() => {
      if (Date.now() - lastFrame > WATCHDOG_MS) setStatus('offline')
    }, 5_000)
    const beat = () => {
      if (presence) void sendPresence(sessionId, focusRef.current).catch(() => undefined)
    }
    beat()
    const heartbeat = window.setInterval(beat, HEARTBEAT_MS)
    return () => {
      source.close()
      window.clearInterval(watchdog)
      window.clearInterval(heartbeat)
      window.clearTimeout(focusTimer.current)
      if (presence) leavePresence(sessionId)
    }
  }, [sessionId, enabled, qc, url, keyString, presence])

  /** Fields report focus here; a change is pushed after a short pause so typing does not spam the server. */
  const setFocus = (field: string | null) => {
    if (!presence || focusRef.current === field) return
    focusRef.current = field
    window.clearTimeout(focusTimer.current)
    focusTimer.current = window.setTimeout(() => void sendPresence(sessionId, focusRef.current).catch(() => undefined), 300)
  }

  return { status, viewers, setFocus }
}
