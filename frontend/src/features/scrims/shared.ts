import type { CSSProperties } from 'react'
import clsx from 'clsx'
import type { Tone } from '@/components/ui'
import type { RoundDoc, SetDoc, ShipOut, ViewerOut } from '@/lib/api/client'

/** What the viewer may do on the live page; derived once from /api/me. */
/** `locked`: an archived scrim, read-only for everyone (the server refuses every write). */
export type Perms = { edit: boolean; manage: boolean; score: boolean; locked: boolean; userId: number | null }

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
/** The sheet's warp-in colour scale: pale yellow at 0 km, light green at 25, blue at 50 and beyond. */
export const WARP_STOPS: { km: number; color: string }[] = [
  { km: 0, color: '#fdfdc9' },
  { km: 25, color: '#c6f5a6' },
  { km: 50, color: '#8fb5ee' },
]

function mix(a: string, b: string, t: number): string {
  const ch = (hex: string, i: number) => parseInt(hex.slice(i, i + 2), 16)
  const out = [1, 3, 5].map((i) => Math.round(ch(a, i) + (ch(b, i) - ch(a, i)) * t))
  return `#${out.map((n) => n.toString(16).padStart(2, '0')).join('')}`
}

export function warpColor(km: number | null | undefined): string | undefined {
  if (km == null) return undefined
  const stops = WARP_STOPS
  if (km <= stops[0].km) return stops[0].color
  for (let i = 1; i < stops.length; i++) {
    if (km <= stops[i].km) return mix(stops[i - 1].color, stops[i].color, (km - stops[i - 1].km) / (stops[i].km - stops[i - 1].km))
  }
  return stops[stops.length - 1].color
}

/** A number input without the browser's spinner arrows. */
export { NO_SPINNER } from '@/lib/styles'

/** Focus another row's hull box in the same lineup table; rows are 1..N, anything outside is ignored. */
export function focusShipRow(table: 'ours' | 'theirs', slotNo: number) {
  document.querySelector<HTMLInputElement>(`[data-testid="scrim.${table}.row.${slotNo}.ship"]`)?.focus()
}

/** Link script fills by burst family, as the sheet colours them: armor orange, shield blue, skirmish green, info grey. */
export const LINK_FAMILY_COLORS: Record<string, string> = { armor: '#ffbba6', shield: '#b1d0fe', skirmish: '#c6f5a6', info: '#e0e0e0' }

export function linkColor(code: string, scripts: { code: string; family: string }[]): string | undefined {
  const family = scripts.find((l) => l.code === code)?.family
  return family ? LINK_FAMILY_COLORS[family] : undefined
}

/** Where a person left a scrim page: selected set and the round per set, kept in the browser. The pilot card reads it too. */
export type Position = { setId: number | null; roundBySet: Record<number, number> }

export function readPosition(scrimId: number): Position | null {
  try {
    const raw = window.localStorage.getItem(`attool.scrim.${scrimId}`)
    return raw ? (JSON.parse(raw) as Position) : null
  } catch {
    return null
  }
}

export function writePosition(scrimId: number, position: Position) {
  try {
    window.localStorage.setItem(`attool.scrim.${scrimId}`, JSON.stringify(position))
  } catch {
    // storage blocked or full: the page still works, it just forgets
  }
}
