import type { SessionOut, SetDoc } from '@/lib/api/client'
import { Badge, Empty, Mono, Panel, Table } from '@/components/ui'
import { diffClass, fmtDiff, outcomeLetter, outcomeTone } from './shared'

type PilotLine = { name: string; hulls: Set<string>; rounds: number; deaths: number }

function pilotLines(sets: SetDoc[]): PilotLine[] {
  const by = new Map<string, PilotLine>()
  for (const s of sets)
    for (const r of s.rounds) {
      if (r.outcome === 'reset') continue
      for (const slot of r.us.slots) {
        if (slot.type_id == null) continue
        const key = slot.pilot_name ?? `slot ${slot.slot_no}`
        const line = by.get(key) ?? { name: key, hulls: new Set<string>(), rounds: 0, deaths: 0 }
        if (slot.ship_name) line.hulls.add(slot.ship_name)
        line.rounds += 1
        if (slot.died) line.deaths += 1
        by.set(key, line)
      }
    }
  return [...by.values()].sort((a, b) => b.rounds - a.rounds || a.name.localeCompare(b.name))
}

/** The night read back: what was banned, how each round went, who died. Everything comes from the set documents. */
export function ReviewView({ scrim }: { scrim: SessionOut }) {
  const sets = scrim.sets
  const rounds = sets.flatMap((s) => s.rounds.filter((r) => r.outcome !== 'reset'))
  const record = { wins: rounds.filter((r) => r.outcome === 'win').length, losses: rounds.filter((r) => r.outcome === 'loss').length, draws: rounds.filter((r) => r.outcome === 'draw').length }
  const total = rounds.reduce((n, r) => n + r.score.differential, 0)
  const pilots = pilotLines(sets)
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2" data-testid="scrim.review">
      <Panel title="Night">
        {sets.length === 0 ? (
          <Empty>No sets were played.</Empty>
        ) : (
          <div className="flex flex-wrap items-center gap-4 text-[12px]">
            <span>
              <Mono>{sets.length}</Mono> set{sets.length === 1 ? '' : 's'}, <Mono>{rounds.length}</Mono> round{rounds.length === 1 ? '' : 's'}
            </span>
            <span data-testid="scrim.review.record">
              record <Mono>{record.wins}</Mono>
              {'–'}
              <Mono>{record.losses}</Mono>
              {record.draws ? <span className="text-muted"> ({record.draws} draw)</span> : null}
            </span>
            <span>
              total differential <Mono className={diffClass(total > 0 ? 'US' : total < 0 ? 'OPP' : 'TIED', 'none')}>{fmtDiff(total)}</Mono>
            </span>
          </div>
        )}
      </Panel>

      {sets.map((s) => (
        <Panel
          key={s.id}
          title={
            <span className="flex items-center gap-2">
              Set {s.index}
              {s.comp_name ? <span className="font-normal normal-case tracking-normal text-fg">{s.comp_name}</span> : null}
              <Badge tone="accent">Team {s.our_side}</Badge>
              <span className="flex gap-0.5">
                {s.rounds.map((r) => (
                  <Badge key={r.round_no} tone={outcomeTone(r.outcome)}>
                    {outcomeLetter(r.outcome)}
                  </Badge>
                ))}
              </span>
            </span>
          }
          testId={`scrim.review.set.${s.id}`}
        >
          <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
            <span>
              <span className="text-muted">bans </span>
              {s.bans.filter((b) => b.type_id != null).length === 0 ? (
                <span className="text-muted">none</span>
              ) : (
                s.bans
                  .filter((b) => b.type_id != null)
                  .map((b) => (
                    <span key={`${b.side}${b.index}`} className="mr-1.5">
                      <Mono className="text-muted">{b.order}</Mono> {b.ship_name}
                      <span className="text-muted"> ({b.side})</span>
                    </span>
                  ))
              )}
            </span>
            {s.avalanche_bans.some((b) => b.type_id != null) ? (
              <span>
                <span className="text-muted">avalanche </span>
                {s.avalanche_bans
                  .filter((b) => b.type_id != null)
                  .map((b) => (
                    <span key={b.id ?? `${b.side}${b.index}`} className="mr-1.5">
                      {b.ship_name}
                      <span className="text-muted"> ({b.side}, from R{b.in_effect_from_round})</span>
                    </span>
                  ))}
              </span>
            ) : null}
            {s.tactics_note ? <span className="text-muted">tactics: {s.tactics_note}</span> : null}
          </div>
          <Table>
            <thead>
              <tr>
                <th>Round</th>
                <th>Outcome</th>
                <th className="text-right">Diff</th>
                <th>We lost</th>
                <th>They lost</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {s.rounds.map((r) => (
                <tr key={r.round_no} data-testid={`scrim.review.set.${s.id}.round.${r.round_no}`}>
                  <td>
                    <Mono>R{r.round_no}</Mono>
                  </td>
                  <td>
                    <Badge tone={outcomeTone(r.outcome)}>{r.outcome}</Badge>
                  </td>
                  <td className="text-right">
                    <Mono className={diffClass(r.score.leader, r.score.indicator)}>{fmtDiff(r.score.differential)}</Mono>
                  </td>
                  <td className="whitespace-normal text-[11px]">
                    {r.us.slots
                      .filter((x) => x.died)
                      .map((x) => `${x.ship_name}${x.pilot_name ? ` (${x.pilot_name})` : ''}`)
                      .join(', ') || <span className="text-muted">nothing</span>}
                    <Mono className="ml-1 text-muted">{r.us.points_lost}</Mono>
                  </td>
                  <td className="whitespace-normal text-[11px]">
                    {r.opp.slots
                      .filter((x) => x.died)
                      .map((x) => x.ship_name)
                      .join(', ') || <span className="text-muted">nothing</span>}
                    <Mono className="ml-1 text-muted">{r.opp.points_lost}</Mono>
                  </td>
                  <td className="whitespace-normal text-[11px]">{r.notes}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      ))}

      {pilots.length ? (
        <Panel title="Pilots" testId="scrim.review.pilots">
          <Table>
            <thead>
              <tr>
                <th>Pilot</th>
                <th>Flew</th>
                <th className="text-right">Rounds</th>
                <th className="text-right">Deaths</th>
                <th className="text-right">Survived</th>
              </tr>
            </thead>
            <tbody>
              {pilots.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td className="whitespace-normal text-[11px] text-muted">{[...p.hulls].join(', ')}</td>
                  <td className="text-right">
                    <Mono>{p.rounds}</Mono>
                  </td>
                  <td className="text-right">
                    <Mono className={p.deaths ? 'text-bad' : ''}>{p.deaths}</Mono>
                  </td>
                  <td className="text-right">
                    <Mono>{Math.round((100 * (p.rounds - p.deaths)) / p.rounds)}%</Mono>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      ) : null}
    </div>
  )
}
