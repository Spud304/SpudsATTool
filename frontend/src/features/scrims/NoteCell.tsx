import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'
import type { Live } from './shared'
import { remoteProps } from './shared'
import { useDebouncedField } from './useDebouncedField'

const EDITOR_WIDTH = 460
const EDITOR_MARGIN = 12

/**
 * A spreadsheet-style note cell: one clipped line in the table; click it and it opens over the
 * neighbouring cells as a wide box showing the whole text. Read-only cells open the same way.
 * The open box is portalled to the body so the table's own scroll box never clips it.
 */
export function NoteCell({
  value,
  onSave,
  readOnly = false,
  placeholder = 'note',
  width = 'w-44',
  testId,
  live,
  field,
}: {
  value: string
  onSave?: (value: string) => void
  readOnly?: boolean
  placeholder?: string
  width?: string
  testId: string
  live?: Live
  field?: string
}) {
  const anchor = useRef<HTMLButtonElement>(null)
  const [box, setBox] = useState<{ top: number; left: number; width: number } | null>(null)
  const draft = useDebouncedField(value, (v) => onSave?.(v))
  const remote = live && field ? remoteProps(live, field) : {}

  const open = () => {
    const rect = anchor.current?.getBoundingClientRect()
    if (!rect) return
    const width = Math.max(rect.width, Math.min(EDITOR_WIDTH, window.innerWidth - 2 * EDITOR_MARGIN))
    const left = Math.min(rect.left, window.innerWidth - width - EDITOR_MARGIN) // slide left when near the edge
    setBox({ top: rect.top, left: Math.max(left, EDITOR_MARGIN), width })
  }
  const close = () => {
    draft.onBlur()
    setBox(null)
    live?.setFocus(null)
  }

  return (
    <>
      <button
        ref={anchor}
        type="button"
        data-testid={testId}
        title={value || undefined}
        onClick={open}
        style={remote.style}
        className={clsx(
          'block h-6 truncate rounded border px-2 text-left text-[12px]',
          width,
          readOnly ? 'border-transparent text-muted hover:border-line' : 'border-line bg-bg text-fg hover:border-muted',
          !value && 'text-muted',
        )}
      >
        {value || (readOnly ? '' : placeholder)}
      </button>
      {box
        ? createPortal(
            <textarea
              autoFocus
              data-testid={`${testId}.editor`}
              readOnly={readOnly}
              rows={3}
              style={{ position: 'fixed', top: box.top, left: box.left, width: box.width, fontFamily: 'var(--font-sans)' }}
              className="z-50 resize-none rounded border border-accent bg-bg p-2 text-[12px] leading-snug text-fg shadow-lg focus:outline-none"
              value={readOnly ? value : draft.value}
              onChange={(e) => draft.onChange(e.target.value)}
              onFocus={() => {
                draft.onFocus()
                if (field) live?.setFocus(field)
              }}
              onBlur={close}
              onKeyDown={(e) => {
                if (e.key === 'Escape' || (e.key === 'Enter' && !e.shiftKey)) {
                  e.preventDefault()
                  ;(e.target as HTMLTextAreaElement).blur()
                }
              }}
            />,
            document.body,
          )
        : null}
    </>
  )
}
