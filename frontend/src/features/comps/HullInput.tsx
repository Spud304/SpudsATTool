import { useEffect, useState } from 'react'
import type { ShipOut } from '@/lib/api/client'
import { Input } from '@/components/ui'

/** Datalist-backed hull picker; commits on blur or Enter, reverts unknown names. Needs a <datalist id={listId}>. */
export function HullInput({
  value,
  lookup,
  onPick,
  listId = 'hulls',
  className = 'w-56',
}: {
  value: string
  lookup: Map<string, ShipOut>
  onPick: (s: ShipOut | null) => void
  listId?: string
  className?: string
}) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  const commit = () => {
    const t = text.trim()
    if (t === '') return onPick(null)
    const s = lookup.get(t)
    if (s) onPick(s)
    else setText(value)
  }
  return (
    <Input
      list={listId}
      className={className}
      invalid={Boolean(text) && !lookup.has(text.trim())}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && commit()}
      placeholder="hull"
    />
  )
}
