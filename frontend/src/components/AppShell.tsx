import type { ReactNode } from 'react'
import { Link, useLocation } from '@tanstack/react-router'
import clsx from 'clsx'
import { useMe, useRulesets, useTeamMutations } from '@/lib/api/hooks'
import { Badge, LinkButton, Mono, Select } from '@/components/ui'

type NavItem = { to: string; label: string; id: string; show: (me: ReturnType<typeof useMe>['data']) => boolean }

const NAV: NavItem[] = [
  { to: '/', label: 'Home', id: 'home', show: () => true },
  { to: '/scratchpad', label: 'Comp scratchpad', id: 'scratchpad', show: (me) => Boolean(me?.membership) },
  { to: '/comps', label: 'Comps', id: 'comps', show: (me) => Boolean(me?.capabilities?.browse_library) },
  { to: '/fits', label: 'Fits', id: 'fits', show: (me) => Boolean(me?.capabilities?.browse_library) },
  { to: '/team', label: 'Team', id: 'team', show: (me) => Boolean(me?.membership) },
  { to: '/team/audit', label: 'Audit', id: 'audit', show: (me) => Boolean(me?.capabilities?.view_audit) },
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
              data-testid={`nav.${n.id}`}
              className={clsx('rounded px-2 py-1 text-muted hover:bg-panel-2 hover:text-fg', pathname === n.to && 'bg-panel-2 text-fg')}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-muted">
          {me.data?.membership ? <RulesetSwitcher active={me.data.team?.active_ruleset ?? null} canSwitch={Boolean(me.data.capabilities?.manage_team)} /> : null}
          {me.isLoading ? null : me.data?.authenticated ? (
            <>
              <span>
                <span data-testid="shell.user">{me.data.display_name}</span>{' '}
                {me.data.membership ? <Badge tone="accent" testId="shell.role">{me.data.membership.role}</Badge> : <Badge tone="warn" testId="shell.role">no membership</Badge>}
              </span>
              <a href="/auth/logout" className="hover:text-fg" data-testid="shell.logout">
                Log out
              </a>
            </>
          ) : (
            <LinkButton href={`/auth/login?next=${encodeURIComponent(pathname)}`} testId="shell.login">
              Log in with EVE Online
            </LinkButton>
          )}
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto p-4">{children}</main>
      <footer className="flex h-6 items-center justify-end border-t border-line px-3 text-[11px] text-muted">attool {me.data?.version ?? ''}</footer>
    </div>
  )
}

/** The season the team is working in; admins switch it here, everyone else just sees it. */
function RulesetSwitcher({ active, canSwitch }: { active: string | null; canSwitch: boolean }) {
  const rulesets = useRulesets()
  const { patchTeam } = useTeamMutations()
  if (!canSwitch) {
    return active ? (
      <span title="active ruleset">
        <Mono className="text-fg" testId="shell.season">
          {active}
        </Mono>
      </span>
    ) : null
  }
  const codes = rulesets.data?.map((r) => r.code) ?? (active ? [active] : [])
  return (
    <span className="flex items-center gap-1" title="active ruleset (admins can switch)">
      <span className="text-[11px]">season</span>
      <Select data-testid="shell.season" value={active ?? ''} disabled={patchTeam.isPending || !rulesets.data} onChange={(e) => patchTeam.mutate({ active_ruleset: e.target.value })}>
        {codes.map((code) => (
          <option key={code} value={code}>
            {code}
          </option>
        ))}
      </Select>
    </span>
  )
}
