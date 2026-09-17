import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'

export type MenuItem = { label: string; onClick: () => void; disabled?: boolean; reason?: string; danger?: boolean }

/**
 * Right-click (or the hover "..." button) on set cards and round tabs. One menu, two ways in, so the
 * fast path exists for people used to the sheet and the button is there for everyone else.
 */
export function useContextMenu() {
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null)
  const open = (e: MouseEvent, items: MenuItem[]) => {
    e.preventDefault()
    e.stopPropagation()
    setMenu({ x: e.clientX, y: e.clientY, items })
  }
  const close = () => setMenu(null)
  useEffect(() => {
    if (!menu) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close()
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', onKey)
    window.addEventListener('scroll', close, true)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', close, true)
    }
  }, [menu])
  const element: ReactNode = menu
    ? createPortal(
        <div
          data-testid="scrim.menu"
          role="menu"
          onMouseDown={(e) => e.stopPropagation()}
          style={{ position: 'fixed', top: Math.min(menu.y, window.innerHeight - 40 * menu.items.length - 12), left: Math.min(menu.x, window.innerWidth - 200) }}
          className="z-50 min-w-[160px] rounded border border-line bg-panel py-1 text-[12px] shadow-lg"
        >
          {menu.items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              data-testid={`scrim.menu.${item.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
              disabled={item.disabled}
              title={item.disabled ? item.reason : undefined}
              onClick={() => {
                close()
                item.onClick()
              }}
              className={clsx('block w-full px-3 py-1.5 text-left hover:bg-panel-2 disabled:cursor-default disabled:opacity-50 disabled:hover:bg-transparent', item.danger && 'text-bad')}
            >
              {item.label}
              {item.disabled && item.reason ? <span className="block text-[10px] text-muted">{item.reason}</span> : null}
            </button>
          ))}
        </div>,
        document.body,
      )
    : null
  return { open, element }
}

/** The hover affordance next to a card or tab; sized to the small tabs so it never shifts the layout. */
export function MenuDots({ onClick, testId, always = false }: { onClick: (e: MouseEvent) => void; testId: string; always?: boolean }) {
  return (
    <button type="button" data-testid={testId} title="more" onClick={onClick} className={clsx('rounded px-1 text-[12px] leading-none text-muted hover:bg-panel-2 hover:text-fg', !always && 'opacity-0 focus:opacity-100 group-hover:opacity-100')}>
      {'⋯'}
    </button>
  )
}
