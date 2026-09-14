import type { ReactNode } from 'react'
import { Link, useLocation } from '@tanstack/react-router'
import clsx from 'clsx'
import { useMe } from '@/lib/api/hooks'
import { Badge, LinkButton } from '@/components/ui'

type NavItem = { to: string; label: string; show: (me: ReturnType<typeof useMe>['data']) => boolean }

const NAV: NavItem[] = [
  { to: '/', label: 'Home', show: () => true },
  { to: '/scratchpad', label: 'Comp scratchpad', show: (me) => Boolean(me?.membership) },
  { to: '/fits', label: 'Fits', show: (me) => Boolean(me?.capabilities?.browse_library) },
  { to: '/team', label: 'Team', show: (me) => Boolean(me?.membership) },
  { to: '/team/audit', label: 'Audit', show: (me) => Boolean(me?.capabilities?.view_audit) },
]

export function AppShell({ children }: { children: ReactNode }) {
  const me = useMe()
  const { pathname } = useLocation()
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-10 items-center gap-4 border-b border-line bg-panel px-3">
        <Link to="/" className="font-semibold tracking-tight">
          {me.data?.team?.name ?? 'AT Tool'}
        </Link>
        <nav className="flex items-center gap-1">
          {NAV.filter((n) => n.show(me.data)).map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={clsx('rounded px-2 py-1 text-muted hover:bg-panel-2 hover:text-fg', pathname === n.to && 'bg-panel-2 text-fg')}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-muted">
          {me.isLoading ? null : me.data?.authenticated ? (
            <>
              <span>
                {me.data.display_name} {me.data.membership ? <Badge tone="accent">{me.data.membership.role}</Badge> : <Badge tone="warn">no membership</Badge>}
              </span>
              <a href="/auth/logout" className="hover:text-fg">
                Log out
              </a>
            </>
          ) : (
            <LinkButton href={`/auth/login?next=${encodeURIComponent(pathname)}`}>Log in with EVE Online</LinkButton>
          )}
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto p-4">{children}</main>
      <footer className="flex h-6 items-center justify-end border-t border-line px-3 text-[11px] text-muted">attool {me.data?.version ?? ''}</footer>
    </div>
  )
}
