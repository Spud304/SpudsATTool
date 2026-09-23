import { useEffect, useRef, useState } from 'react'
import type { ShipOut } from '@/lib/api/client'
import { Input } from '@/components/ui'

/** Datalist-backed hull picker; commits on blur or Enter, reverts unknown names. Needs a <datalist id={listId}>. */
export function HullInput({
  value,
  lookup,
  onPick,
  listId = 'hulls',
  className = 'w-56',
  testId,
  onEnter,
  onArrow,
}: {
  value: string
  lookup: Map<string, ShipOut>
  onPick: (s: ShipOut | null) => void
  listId?: string
  className?: string
  testId?: string
  /** Called after Enter commits, e.g. to move focus to the next row. */
  onEnter?: () => void
  /** Up/Down between rows; only while not mid-edit, so the suggestion list keeps its arrow keys. */
  onArrow?: (direction: -1 | 1) => void
}) {
  const [text, setText] = useState(value)
  const skipBlur = useRef(false)
  useEffect(() => setText(value), [value])
  const commit = () => {
    const t = text.trim()
    if (t === value.trim()) return // unchanged: tabbing through must not save or reset anything
    if (t === '') return onPick(null)
    const s = lookup.get(t)
    if (s) onPick(s)
    else setText(value)
  }
  return (
    <Input
      data-testid={testId}
      list={listId}
      className={className}
      invalid={Boolean(text) && !lookup.has(text.trim())}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        if (skipBlur.current) {
          skipBlur.current = false
          return
        }
        commit()
      }}
      onKeyDown={(e) => {
        if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && onArrow && text === value) {
          e.preventDefault()
          // Moving focus blurs us synchronously; nothing was typed, so skip that blur. Reset right
          // after, because at the first or last row focus does not move and no blur comes.
          skipBlur.current = true
          onArrow(e.key === 'ArrowDown' ? 1 : -1)
          skipBlur.current = false
          return
        }
        if (e.key !== 'Enter') return
        commit()
        if (onEnter) {
          skipBlur.current = true // the value is already committed
          onEnter()
          skipBlur.current = false
        }
      }}
      placeholder="hull"
    />
  )
}
