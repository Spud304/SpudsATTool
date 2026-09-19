import { Link } from '@tanstack/react-router'
import { useComps, useFits, useHealth, useMe, useScrims } from '@/lib/api/hooks'
import { Badge, Empty, LinkButton, Mono, PageHeader, Panel } from '@/components/ui'
import { RsvpButtons } from '@/features/scrims/RsvpButtons'
import { whenAt } from '@/features/scrims/format'
import { usePageTitle } from '@/hooks/usePageTitle'

export function DashboardPage() {
  usePageTitle('Home')
  const me = useMe()
  const health = useHealth()

  if (me.isLoading) return <p className="text-muted">Loading…</p>

  if (!me.data?.authenticated) {
    return (
      <div className="mx-auto mt-16 max-w-lg">
        <Panel>
          <h1 className="mb-2 text-lg font-semibold">Team organizer</h1>
          <p className="mb-4 text-muted">Comps, fits, scrims and statistics for an EVE Online tournament team.</p>
          {me.data?.sso_configured ? (
            <LinkButton href="/auth/login?next=/">Log in with EVE Online</LinkButton>
          ) : (
            <p className="text-warn">EVE SSO is not configured: set EVE_CLIENT_ID and EVE_CLIENT_SECRET.</p>
          )}
          {me.data && !me.data.admins_configured ? (
            <p className="mt-3 text-body text-warn">No admins configured: set ADMIN_CHARACTER_IDS before anyone can log in.</p>
          ) : null}
        </Panel>
      </div>
    )
  }

  if (!me.data.membership) {
    return (
      <div className="mx-auto mt-16 max-w-lg">
        <Panel title="Not a member">
          <p className="text-muted">{me.data.display_name}, your character is not an active member of this team. Ask your captain.</p>
        </Panel>
      </div>
    )
  }

  return (
    <>
      <PageHeader title="Home" context={<span>{me.data.team?.name}</span>} />
    <div className="grid gap-4 lg:grid-cols-3">
      <Panel title="You">
        <p>
          {me.data.display_name} <Badge tone="accent">{me.data.membership.role}</Badge>
          {me.data.membership.is_leadership ? <Badge tone="info">leadership</Badge> : null}
        </p>
        <ul className="mt-2 space-y-1">
          {me.data.characters.map((c) => (
            <li key={c.character_id} className="flex items-center gap-2">
              <span>{c.name}</span>
              <Mono className="text-muted">{c.character_id}</Mono>
              {c.is_main ? <Badge>main</Badge> : null}
            </li>
          ))}
        </ul>
        <a href="/auth/login?mode=link&next=/" className="mt-3 inline-block text-accent">
          Link another character
        </a>
      </Panel>
      <Panel title="Server">
        <ul className="space-y-1 text-muted">
          <li>
            SDE build <Mono>{health.data?.sde_build ?? 'none'}</Mono> {health.data?.sde_stale ? <Badge tone="warn">stale</Badge> : <Badge tone="ok">fresh</Badge>}
          </li>
          <li>
            version <Mono>{health.data?.version}</Mono>
          </li>
        </ul>
      </Panel>
      {me.data.capabilities?.browse_scrims ? <UpcomingScrimsPanel /> : null}
      {me.data.capabilities?.manage_library ? <ReviewQueuePanel /> : null}
      {me.data.capabilities?.manage_members ? (
        <Panel title="Next steps">
          <ul className="space-y-1">
            <li>
              <Link to="/team" className="text-accent">
                Invite members or add an admission rule
              </Link>
            </li>
            <li>
              <Link to="/scratchpad" className="text-accent">
                Evaluate a comp against the imported rulesets
              </Link>
            </li>
          </ul>
        </Panel>
      ) : null}
    </div>
    </>
  )
}

/** Member proposals waiting for a theorycrafter: suggested fits and comps. */
function ReviewQueuePanel() {
  const fits = useFits({ status: 'suggested' })
  const comps = useComps({ status: 'suggested' })
  const total = (fits.data?.length ?? 0) + (comps.data?.length ?? 0)
  return (
    <Panel title={`Review queue${total ? ` (${total})` : ''}`} testId="dash.review">
      {total === 0 ? (
        <p className="text-muted">Nothing suggested right now.</p>
      ) : (
        <ul className="space-y-1">
          {(comps.data ?? []).slice(0, 5).map((c) => (
            <li key={`c${c.id}`} data-testid={`dash.review.item.comp.${c.id}`}>
              <Link to="/comps/$compId" params={{ compId: String(c.id) }} className="text-accent">
                comp: {c.name}
              </Link>
              <span className="text-muted"> by {c.created_by_name || 'unknown'}</span>
            </li>
          ))}
          {(fits.data ?? []).slice(0, 5).map((f) => (
            <li key={`f${f.id}`} data-testid={`dash.review.item.fit.${f.id}`}>
              <Link to="/fits/$fitId" params={{ fitId: String(f.id) }} className="text-accent">
                fit: {f.ship_name} / {f.name}
              </Link>
              <span className="text-muted"> by {f.created_by_name || 'unknown'}</span>
            </li>
          ))}
          {total > 10 ? (
            <li className="text-muted">
              and more in <Link to="/comps" className="text-accent">Comps</Link> and <Link to="/fits" className="text-accent">Fits</Link>
            </li>
          ) : null}
        </ul>
      )}
    </Panel>
  )
}

/** The next few nights, with the viewer's own RSVP right on the card. */
function UpcomingScrimsPanel() {
  const scrims = useScrims('upcoming')
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_scrims)
  return (
    <Panel
      title="Upcoming scrims"
      testId="dash.scrims"
      actions={
        <Link to="/scrims" className="text-[11px] text-accent">
          all scrims
        </Link>
      }
    >
      {scrims.data?.length ? (
        <ul className="space-y-2">
          {scrims.data.slice(0, 5).map((s) => (
            <li key={s.id} data-testid={`dash.scrims.item.${s.id}`} className="flex flex-wrap items-center gap-2">
              <Link to="/scrims/$scrimId" params={{ scrimId: String(s.id) }} className="text-accent">
                {s.title}
              </Link>
              <span className="text-muted">
                {whenAt(s.date)}
                {s.opponent_name ? ` vs ${s.opponent_name}` : ''}
              </span>
              <RsvpButtons scrim={s} testPrefix={`dash.scrims.item.${s.id}`} />
            </li>
          ))}
        </ul>
      ) : scrims.isLoading ? (
        <Empty>Loading…</Empty>
      ) : (
        <Empty
          testId="dash.scrims.empty"
          hint={canManage ? undefined : 'Captains add scrims on the Scrims page.'}
          action={
            canManage ? (
              <Link to="/scrims" className="text-accent" data-testid="dash.scrims.new">
                Schedule a scrim
              </Link>
            ) : undefined
          }
        >
          Nothing scheduled.
        </Empty>
      )}
    </Panel>
  )
}
