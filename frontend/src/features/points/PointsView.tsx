import { useCallback, useMemo, useState } from 'react'
import clsx from 'clsx'
import type { ShipOut } from '@/lib/api/client'
import { useRulesetShips } from '@/lib/api/hooks'
import { Badge, Button, Empty, ErrorText, Input, Mono, Select, Table } from '@/components/ui'
import { sortRows, useSort, type SortState } from '@/hooks/useSort'
import { NO_SPINNER } from '@/lib/styles'

type SortKey = 'name' | 'family' | 'sizeRank' | 'points'
type Filters = {
  text: string
  hull_size: string
  min: string
  max: string
}

const EMPTY_FILTERS: Filters = {
  text: '',
  hull_size: '',
  min: '',
  max: '',
}
const FILTER_KEYS = Object.keys(EMPTY_FILTERS) as (keyof Filters)[]
const DEFAULT_SORT: SortState<SortKey> = { key: 'points', dir: 'desc' }

/** Remembered filters may come from an older version of this view; keep only the keys that still exist. */
function restoreFilters(saved: Partial<Filters> | undefined): Filters {
  const out = { ...EMPTY_FILTERS }
  for (const k of FILTER_KEYS) if (typeof saved?.[k] === 'string') out[k] = saved[k] as string
  return out
}

type Saved = { sort: SortState<SortKey>; filters: Filters }

function readSaved(code: string): Saved | null {
  try {
    const raw = window.localStorage.getItem(`attool.points.${code}`)
    return raw ? (JSON.parse(raw) as Saved) : null
  } catch {
    return null
  }
}

function writeSaved(code: string, saved: Saved) {
  try {
    window.localStorage.setItem(`attool.points.${code}`, JSON.stringify(saved))
  } catch {
    // storage unavailable: the view still works, it just forgets
  }
}

const byName = (s: ShipOut) => s.name

// The official points list names some rows per hull ("Cobra (Recon Unique)"); the general type in the
// brackets is what the size and class limits are written against. Two rows word a type differently.
const FAMILY_ALIASES: Record<string, string> = { Recon: 'Recon Ship', 'Covert Ops': 'Covert Ops Ship' }

export function familyOf(s: ShipOut): string | null {
  if (!s.ship_class) return null
  const m = /^(.+?) \((.+)\)$/.exec(s.ship_class)
  const raw = m && m[1] === s.name ? m[2] : s.ship_class
  const family = raw.replace(/,?\s*Unique$/, '').trim()
  return FAMILY_ALIASES[family] ?? family
}

type Row = ShipOut & { family: string | null; sizeRank: number }

// Hull sizes from biggest to smallest; the dropdown and the Size column follow this, not the alphabet.
const SIZE_ORDER = ['FLAG', 'BS', 'BC', 'LC', 'CR', 'IN', 'DE', 'LF', 'FR', 'CV']
const sizeRank = (size: string | null) => {
  const i = size ? SIZE_ORDER.indexOf(size) : -1
  return i === -1 ? -1 : SIZE_ORDER.length - i
}

/**
 * Every hull in a ruleset with class, size and points; sortable and filterable.
 * `compact` drops the Class column and the badges so it fits the scratchpad's side column; every filter stays;
 * `onPick` makes rows clickable (the scratchpad fills its next empty slot).
 */
export function PointsView({ code, compact = false, onPick }: { code: string; compact?: boolean; onPick?: (ship: ShipOut) => void }) {
  const ships = useRulesetShips(code)
  const saved = useMemo(() => readSaved(code), [code])
  const [filters, setFilters] = useState<Filters>(() => restoreFilters(saved?.filters))
  const { sort, toggle } = useSort<SortKey>(saved?.sort ?? DEFAULT_SORT, (next) => writeSaved(code, { sort: next, filters }))
  const update = (patch: Partial<Filters>) => {
    const next = { ...filters, ...patch }
    setFilters(next)
    writeSaved(code, { sort, filters: next })
  }
  const clear = () => update(EMPTY_FILTERS)

  // Banned hulls are left out: the viewer answers what a legal comp can field.
  const all = useMemo<Row[]>(() => (ships.data ?? []).filter((s) => s.legality === 'legal').map((s) => ({ ...s, family: familyOf(s), sizeRank: sizeRank(s.hull_size) })), [ships.data])
  const sizes = useMemo(() => [...new Set(all.map((s) => s.hull_size).filter((c): c is string => Boolean(c)))].sort((a, b) => sizeRank(b) - sizeRank(a) || a.localeCompare(b)), [all])

  const filtered = useMemo(() => {
    const text = filters.text.trim().toLowerCase()
    const min = filters.min === '' ? null : Number(filters.min)
    const max = filters.max === '' ? null : Number(filters.max)
    return all.filter((s) => {
      if (text && !s.name.toLowerCase().includes(text) && !(s.family ?? '').toLowerCase().includes(text)) return false
      if (filters.hull_size && s.hull_size !== filters.hull_size) return false
      if (min != null && (s.points == null || s.points < min)) return false
      if (max != null && (s.points == null || s.points > max)) return false
      return true
    })
  }, [all, filters])
  const sortKey = sort.key
  const pick = useCallback((s: Row) => s[sortKey], [sortKey])
  const rows = useMemo(() => sortRows(filtered, sort.dir, pick, byName), [filtered, sort.dir, pick])
  const active = FILTER_KEYS.some((k) => filters[k] !== EMPTY_FILTERS[k])

  if (ships.error) return <ErrorText error={ships.error} testId="points.error" />
  if (!ships.data) return <Empty>Loading hulls…</Empty>

  const header = (key: SortKey, label: string, right = false, defaultDir: 'asc' | 'desc' = 'asc') => (
    <th className={clsx(right && 'text-right')}>
      <button
        type="button"
        onClick={() => toggle(key, defaultDir)}
        data-testid={`points.sort.${key}`}
        data-dir={sort.key === key ? sort.dir : undefined}
        className={clsx('inline-flex items-center gap-1 uppercase hover:text-fg', sort.key === key && 'text-fg')}
      >
        {label}
        {sort.key === key ? <span aria-hidden>{sort.dir === 'asc' ? '▲' : '▼'}</span> : null}
      </button>
    </th>
  )

  return (
    <div className="space-y-2" data-testid="points">
      <div className="flex flex-wrap items-center gap-2">
        <Input placeholder="hull or class" value={filters.text} onChange={(e) => update({ text: e.target.value })} data-testid="points.filter.text" className="w-44" />
        <>
          <Select value={filters.hull_size} onChange={(e) => update({ hull_size: e.target.value })} data-testid="points.filter.size">
            <option value="">all sizes</option>
            {sizes.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
          <span className="flex items-center gap-1 text-[12px] text-muted" title="Both ends included: a hull shows when min ≤ points ≤ max.">
            pts
            <Input
              type="number"
              inputMode="numeric"
              placeholder="min"
              value={filters.min}
              onChange={(e) => update({ min: e.target.value })}
              data-testid="points.filter.min"
              className={clsx('w-16', NO_SPINNER)}
            />
            to
            <Input
              type="number"
              inputMode="numeric"
              placeholder="max"
              value={filters.max}
              onChange={(e) => update({ max: e.target.value })}
              data-testid="points.filter.max"
              className={clsx('w-16', NO_SPINNER)}
            />
            <span className="text-[11px]">(inclusive)</span>
          </span>
        </>
        <span className="text-[12px] text-muted" data-testid="points.count">
          {rows.length} of {all.length} hulls
        </span>
        {active ? (
          <Button variant="default" onClick={clear} data-testid="points.clear">
            Clear filters
          </Button>
        ) : null}
      </div>
      <Table className={compact ? 'max-h-[50vh] overflow-y-auto' : undefined}>
        <thead>
          <tr>
            {header('name', 'Ship')}
            {compact ? null : header('family', 'Class')}
            {header('sizeRank', 'Size', false, 'desc')}
            {header('points', 'Points', true, 'desc')}
            {compact ? null : <th>Flags</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr
              key={s.type_id}
              data-testid={`points.row.${s.type_id}`}
              onClick={onPick ? () => onPick(s) : undefined}
              className={clsx(onPick && 'cursor-pointer hover:bg-panel-2')}
              title={onPick ? 'add to the next empty slot' : undefined}
            >
              <td>{s.name}</td>
              {compact ? null : (
                <td className="text-muted" title={s.ship_class ?? undefined}>
                  {s.family ?? ''}
                </td>
              )}
              <td>
                <Mono>{s.hull_size ?? ''}</Mono>
              </td>
              <td className="text-right">
                <Mono>{s.points ?? '—'}</Mono>
              </td>
              {compact ? null : (
                <td className="space-x-1">
                  {s.is_unique ? <Badge tone="warn">unique</Badge> : null}
                  {s.flagship_eligible ? <Badge tone="accent">flagship</Badge> : null}
                </td>
              )}
            </tr>
          ))}
          {rows.length === 0 ? (
            <tr>
              <td colSpan={compact ? 3 : 5} className="text-muted">
                No hulls match.
              </td>
            </tr>
          ) : null}
        </tbody>
      </Table>
    </div>
  )
}
