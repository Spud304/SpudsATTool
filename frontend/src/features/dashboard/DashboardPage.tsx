import { Link } from '@tanstack/react-router'
import { useComps, useFits, useHealth, useMe, useScrims } from '@/lib/api/hooks'
import { Badge, Empty, LinkButton, Mono, PageHeader, Panel } from '@/components/ui'
import { RsvpButtons } from '@/features/scrims/RsvpButtons'
import { record, whenAt } from '@/features/scrims/format'
import { outcomeLetter, outcomeTone } from '@/features/scrims/shared'
import clsx from 'clsx'
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

  const caps = me.data.capabilities
  return (
    <>
      <PageHeader title="Home" context={<span>{me.data.team?.name}</span>} />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          {caps?.browse_scrims ? <NextScrimPanel /> : null}
          {caps?.browse_scrims ? <LastScrimPanel /> : null}
          {caps?.manage_library ? <ReviewQueuePanel /> : null}
        </div>
        <div className="space-y-4">
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
          {caps?.browse_library ? <LibraryHealthPanel /> : null}
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
          {caps?.manage_members ? (
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

/** The next night, large, with the viewer's own RSVP and the tally; the nights after it as a short list. */
function NextScrimPanel() {
  const scrims = useScrims('upcoming')
  const me = useMe()
  const canManage = Boolean(me.data?.capabilities?.manage_scrims)
  const next = scrims.data?.[0]
  const later = scrims.data?.slice(1, 5) ?? []
  return (
    <Panel
      title="Next scrim"
      testId="dash.scrims"
      actions={
        <Link to="/scrims" className="text-[11px] text-accent">
          all scrims
        </Link>
      }
    >
      {next ? (
        <div className="space-y-3">
          <div data-testid={`dash.scrims.item.${next.id}`} className="space-y-2">
            <div className="flex flex-wrap items-baseline gap-2">
              <Link to="/scrims/$scrimId" params={{ scrimId: String(next.id) }} className="text-[16px] font-semibold text-accent" data-testid="dash.next.title">
                {next.title}
              </Link>
              <span className="text-muted">
                {whenAt(next.date)}
                {next.opponent_name ? ` vs ${next.opponent_name}` : ''}
                {next.system_name ? ` in ${next.system_name}` : ''}
              </span>
            </div>
            <RsvpButtons scrim={next} testPrefix={`dash.scrims.item.${next.id}`} />
            <div className="flex flex-wrap gap-1 text-[11px]" data-testid="dash.next.tally">
              <Badge tone="ok">{next.tally.yes} attending</Badge>
              <Badge tone="warn">{next.tally.maybe} maybe</Badge>
              <Badge tone="bad">{next.tally.no} unable</Badge>
              <Badge tone="muted">{next.tally.none} no answer</Badge>
            </div>
          </div>
          {later.length ? (
            <ul className="divide-y divide-line border-t border-line pt-1">
              {later.map((s) => (
                <li key={s.id} data-testid={`dash.scrims.item.${s.id}`} className="flex flex-wrap items-center gap-2 py-1">
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
          ) : null}
        </div>
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

/** The most recent night: record, one row of result pips per set, and the way to its review. */
function LastScrimPanel() {
  const scrims = useScrims('past')
  const last = scrims.data?.find((s) => !s.is_archived) ?? scrims.data?.[0]
  return (
    <Panel title="Last scrim" testId="dash.last">
      {last ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-baseline gap-2">
            <Link to="/scrims/$scrimId" params={{ scrimId: String(last.id) }} className="font-semibold text-accent" data-testid="dash.last.title">
              {last.title}
            </Link>
            <span className="text-muted">
              {whenAt(last.date)}
              {last.opponent_name ? ` vs ${last.opponent_name}` : ''}
            </span>
            <Mono className="ml-auto text-[16px]" testId="dash.last.record">
              {record(last.sets) || '\u2014'}
            </Mono>
          </div>
          {last.sets.length ? (
            <ul className="space-y-1">
              {last.sets.map((set) => (
                <li key={set.id} className="flex flex-wrap items-center gap-2">
                  <Mono className="text-muted">Set {set.index}</Mono>
                  <span>{set.comp_name ?? set.label ?? ''}</span>
                  <span className="flex gap-0.5">
                    {set.outcomes.map((o, i) => (
                      <span
                        key={i}
                        title={`R${i + 1}: ${o}`}
                        className={clsx(
                          'mono inline-flex h-5 w-5 items-center justify-center rounded text-[11px]',
                          outcomeTone(o) === 'ok' && 'bg-ok/15 text-ok',
                          outcomeTone(o) === 'bad' && 'bg-bad/15 text-bad',
                          outcomeTone(o) === 'info' && 'bg-info/15 text-info',
                          outcomeTone(o) === 'muted' && 'bg-panel-2 text-muted',
                        )}
                      >
                        {outcomeLetter(o)}
                      </span>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No sets were recorded.</p>
          )}
        </div>
      ) : scrims.isLoading ? (
        <Empty>Loading…</Empty>
      ) : (
        <Empty hint="Results appear here after the first night.">No scrims yet.</Empty>
      )}
    </Panel>
  )
}

/** Comps and fits that need a look: over cap or illegal under the current table, fits with no parsed stats. */
function LibraryHealthPanel() {
  const comps = useComps({ status: 'active,construction' })
  const fits = useFits({ status: 'active' })
  const broken = (comps.data ?? []).filter((c) => c.evaluation && (c.evaluation.cap_status === 'OVER' || !c.evaluation.is_legal))
  const noStats = (fits.data ?? []).filter((f) => !f.stats_parse_ok)
  const total = broken.length + noStats.length
  return (
    <Panel title={`Library health${total ? ` (${total})` : ''}`} testId="dash.health">
      {comps.isLoading || fits.isLoading ? (
        <Empty>Loading…</Empty>
      ) : total === 0 ? (
        <p className="text-muted" data-testid="dash.health.ok">
          Every active comp fits the cap and is legal; every active fit has stats.
        </p>
      ) : (
        <ul className="space-y-1">
          {broken.slice(0, 6).map((c) => (
            <li key={`c${c.id}`} data-testid={`dash.health.comp.${c.id}`}>
              <Link to="/comps/$compId" params={{ compId: String(c.id) }} className="text-accent">
                {c.name}
              </Link>{' '}
              <Badge tone="bad">{c.evaluation?.cap_status === 'OVER' ? 'over cap' : `${c.evaluation?.error_count ?? 0} errors`}</Badge>
            </li>
          ))}
          {noStats.slice(0, 6).map((f) => (
            <li key={`f${f.id}`} data-testid={`dash.health.fit.${f.id}`}>
              <Link to="/fits/$fitId" params={{ fitId: String(f.id) }} className="text-accent">
                {f.ship_name} / {f.name}
              </Link>{' '}
              <Badge tone="warn">no stats</Badge>
            </li>
          ))}
          {total > 12 ? <li className="text-muted">and {total - 12} more</li> : null}
        </ul>
      )}
    </Panel>
  )
}
