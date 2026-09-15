import type { CSSProperties } from 'react'
import clsx from 'clsx'
import type { Tone } from '@/components/ui'
import type { RoundDoc, SetDoc, ShipOut, ViewerOut } from '@/lib/api/client'

/** What the viewer may do on the live page; derived once from /api/me. */
export type Perms = { edit: boolean; manage: boolean; score: boolean; userId: number | null }

/** Presence plumbing handed to every editable field. */
export type Live = { setFocus: (field: string | null) => void; remote: Map<string, string[]> }

export function remoteFocus(viewers: ViewerOut[], myUserId: number | null): Map<string, string[]> {
  const map = new Map<string, string[]>()
  for (const v of viewers) {
    if (!v.focus || v.user_id === myUserId) continue
    map.set(v.focus, [...(map.get(v.focus) ?? []), v.name])
  }
  return map
}

/** Amber outline when someone else has the field focused; the title names them. Inline style so it never fights a className. */
export function remoteProps(live: Live, field: string): { style?: CSSProperties; title?: string } {
  const names = live.remote.get(field)
  return names ? { style: { outline: '2px solid var(--warn)', outlineOffset: -2 }, title: `${names.join(', ')} editing` } : {}
}

export function focusProps(live: Live, field: string) {
  return { onFocus: () => live.setFocus(field), onBlur: () => live.setFocus(null) }
}

export function fmtDiff(n: number): string {
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '0'
}

export function diffClass(leader: string, indicator: string): string {
  return clsx(leader === 'US' && 'text-ok', leader === 'OPP' && 'text-bad', leader === 'TIED' && 'text-muted', indicator !== 'none' && 'font-semibold')
}

export function outcomeTone(outcome: string): Tone {
  return outcome === 'win' ? 'ok' : outcome === 'loss' ? 'bad' : outcome === 'draw' ? 'info' : 'muted'
}

export function outcomeLetter(outcome: string): string {
  return outcome === 'win' ? 'W' : outcome === 'loss' ? 'L' : outcome === 'draw' ? 'D' : outcome === 'reset' ? 'R' : '·'
}

export function capClass(capStatus: string): string {
  return capStatus === 'OVER' ? 'bg-bad' : capStatus === 'UNDER' ? 'bg-warn' : 'bg-accent'
}

export function currentRound(set: SetDoc, roundNo: number): RoundDoc {
  return set.rounds.find((r) => r.round_no === roundNo) ?? set.rounds[set.rounds.length - 1]
}

export function shipMaps(ships: ShipOut[] | undefined) {
  return {
    byName: new Map((ships ?? []).map((s) => [s.name, s])),
    byId: new Map((ships ?? []).map((s) => [s.type_id, s])),
  }
}

export const HULL_LIST_ID = 'scrim-hulls'

/** Warp-in distance colours, one per 10 km band (0-9, 10-19, 20-29, ...); the last entry covers everything further. */
export const WARP_BAND_COLORS: string[] = ['#9aa5b5', '#4fc38a', '#62c4d9', '#6ea8fe', '#b48cff', '#e8b647', '#ef8f4f', '#ef6b6b', '#d15fb0', '#ffffff']

export function warpColor(km: number | null | undefined): string | undefined {
  if (km == null) return undefined
  return WARP_BAND_COLORS[Math.min(Math.floor(Math.max(km, 0) / 10), WARP_BAND_COLORS.length - 1)]
}

/** A number input without the browser's spinner arrows. */
export const NO_SPINNER = '[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'

/** Focus another row's hull box in the same lineup table; rows are 1..N, anything outside is ignored. */
export function focusShipRow(table: 'ours' | 'theirs', slotNo: number) {
  document.querySelector<HTMLInputElement>(`[data-testid="scrim.${table}.row.${slotNo}.ship"]`)?.focus()
}
