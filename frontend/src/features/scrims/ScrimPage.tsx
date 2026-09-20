import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import clsx from 'clsx'
import type { AttendanceOut, FitSummaryOut, SessionOut, SetDoc, SlotDoc } from '@/lib/api/client'
import {
  useComps,
  useCompVocab,
  useFits,
  useMe,
  usePilots,
  useRulesetShips,
  useScrim,
  useScrimMutations,
  useScrimVocab,
  useSetMutations,
} from '@/lib/api/hooks'
import { Badge, Button, Empty, ErrorText, Mono, Panel } from '@/components/ui'
import { BanBoard } from './BanBoard'
import { FitsColumn } from './FitsColumn'
import { HistoryDrawer } from './HistoryDrawer'
import { OurLineup, pilotOptions } from './OurLineup'
import { ResultsColumn } from './ResultsColumn'
import { ReviewView } from './ReviewView'
import { RoundNotes } from './RoundNotes'
import { RsvpButtons } from './RsvpButtons'
import { SessionForm } from './SessionForm'
import { SetStepper } from './SetStepper'
import { SharePanel } from './SharePanel'
import { TheirLineup } from './TheirLineup'
import { RSVP_LABELS, whenAt } from './format'
import { HULL_LIST_ID, currentRound, readPosition, remoteFocus, shipMaps, writePosition, type Live, type Perms } from './shared'
import { useScrimStream, type StreamStatus } from './useScrimStream'
import { usePageTitle } from '@/hooks/usePageTitle'

/** The live scrim page: rail (header, attendance, sets) | results | bans over ours over theirs | fits. */
export function ScrimPage() {
  usePageTitle('Scrim')
  const { scrimId } = useParams({ from: '/scrims/$scrimId' })
  const id = Number(scrimId)
  const scrim = useScrim(id)
  const me = useMe()
  const stream = useScrimStream(id, Boolean(scrim.data))

  if (scrim.error) return <ErrorText error={scrim.error} />
  if (!scrim.data || !me.data) return <Empty>Loading\u2026</Empty>
  const caps = me.data.capabilities
  const perms: Perms = {
    edit: Boolean(caps?.edit_sets),
    manage: Boolean(caps?.manage_scrims),
    score: Boolean(caps?.score),
    userId: me.data.user_id ?? null,
  }
  return <Board scrim={scrim.data} perms={perms} stream={stream} />
}

export function Board({ scrim, perms, stream, shared = false }: { scrim: SessionOut; perms: Perms; stream: ReturnType<typeof useScrimStream>; shared?: boolean }) {
  // The page comes back to the set and round you were on; the browser keeps it per scrim.
  const remembered = useMemo(() => (shared ? null : readPosition(scrim.id)), [scrim.id, shared])
  const [selectedSetId, setSelectedSetId] = useState<number | null>(remembered?.setId ?? null)
  const [view, setView] = useState<'board' | 'review'>('board')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [roundBySet, setRoundBySet] = useState<Record<number, number>>(remembered?.roundBySet ?? {})
  useEffect(() => {
    if (!shared) writePosition(scrim.id, { setId: selectedSetId, roundBySet })
  }, [scrim.id, shared, selectedSetId, roundBySet])
  const sets = scrim.sets
  const set: SetDoc | null = sets.find((s) => s.id === selectedSetId) ?? sets[sets.length - 1] ?? null
  const round = set ? currentRound(set, roundBySet[set.id] ?? -1) : null
  const selectRound = (setId: number, n: number) => setRoundBySet((old) => ({ ...old, [setId]: n }))

  const ships = useRulesetShips(scrim.ruleset, !shared)
  const { byName } = useMemo(() => shipMaps(ships.data), [ships.data])
  const fits = useFits({ status: 'active' }, !shared)
  const fitsByShip = useMemo(() => {
    const map = new Map<number, FitSummaryOut[]>()
    for (const f of fits.data ?? []) map.set(f.ship_id, [...(map.get(f.ship_id) ?? []), f])
    for (const list of map.values()) list.sort((a, b) => a.name.localeCompare(b.name))
    return map
  }, [fits.data])
  const banned = round?.banned_type_ids ?? []
  const comps = useComps({ status: 'active', banned: banned.length ? banned.join(',') : undefined }, perms.edit)
  const pilots = usePilots('active', !shared)
  const options = useMemo(() => pilotOptions(scrim.attendance, pilots.data ?? []), [scrim.attendance, pilots.data])
  const scrimVocab = useScrimVocab(!shared)
  const compVocab = useCompVocab(!shared)
  const sm = useSetMutations(scrim.id)
  const live: Live = { setFocus: stream.setFocus, remote: remoteFocus(stream.viewers, perms.userId) }
  const online = new Set(stream.viewers.map((v) => v.user_id))
  const error = [sm.patchSet, sm.putBan, sm.addRound, sm.deleteRound, sm.patchRound, sm.patchAssignment, sm.deleteSet, sm.createSet].map((x) => x.error).find(Boolean)

  const m = set
    ? {
        patchSet: (body: Record<string, unknown>) => sm.patchSet.mutate({ setId: set.id, body }),
        putBan: (ban: { side: string; kind: string; index: number; type_id: number | null; in_effect_from_round?: number }) => sm.putBan.mutate({ setId: set.id, ...ban }),
        deleteSet: (reason: string) => sm.deleteSet.mutate({ setId: set.id, reason }),
        addRound: () => sm.addRound.mutate({ setId: set.id }, { onSuccess: (doc) => selectRound(doc.id, doc.rounds[doc.rounds.length - 1].round_no) }),
        deleteRound: (n: number) => sm.deleteRound.mutate({ setId: set.id, roundNo: n }),
        patchRound: (n: number, body: { outcome?: string | null; notes?: string | null }) => sm.patchRound.mutate({ setId: set.id, roundNo: n, body }),
        toggleDied: (n: number, side: 'US' | 'OPP', slot: SlotDoc) => sm.patchAssignment.mutate({ setId: set.id, roundNo: n, side, slotNo: slot.slot_no, body: { died: !slot.died } }),
        patchSlot: (n: number, side: 'US' | 'OPP', slotNo: number, body: Record<string, unknown>) => sm.patchAssignment.mutate({ setId: set.id, roundNo: n, side, slotNo, body }),
        pasteOpp: (n: number, text: string) => sm.pasteOpp.mutateAsync({ setId: set.id, roundNo: n, text }),
      }
    : null

  return (
    <div className="overflow-x-auto">
      <datalist id={HULL_LIST_ID}>{(ships.data ?? []).map((s) => <option key={s.type_id} value={s.name} />)}</datalist>
      {/* Grid for the three left columns so the header and the ban board share a row height, and results starts level
          with ours; the fits column sits outside the grid so its height never stretches the others. */}
      <div className="flex min-w-[1320px] items-start gap-2">
        <div className="grid min-w-0 flex-1 gap-2" style={{ gridTemplateColumns: '230px 210px minmax(0,1fr)', gridTemplateAreas: '"scrim scrim bans" "rail results main"' }}>
          <div style={{ gridArea: 'scrim' }} className="flex">
            <Header scrim={scrim} status={stream.status} className="flex-1" view={view} onView={setView} onHistory={() => setHistoryOpen(true)} onShare={() => setShareOpen(true)} shared={shared} />
          </div>
          <div style={{ gridArea: 'rail' }} className="flex flex-col gap-2 self-start">
            <AttendanceRail scrim={scrim} online={online} />
            <SetStepper
              sets={sets}
              selectedId={set?.id ?? null}
              onSelect={setSelectedSetId}
              perms={perms}
              pending={sm.createSet.isPending}
              error={null}
              onCreate={(copy) => sm.createSet.mutate({ copy_previous: copy, label: '' }, { onSuccess: (doc) => setSelectedSetId(doc.id) })}
              onDelete={(id, reason) => sm.deleteSet.mutate({ setId: id, reason })}
            />
          </div>
          {view === 'review' ? (
            <div style={{ gridArea: 'bans' }} className="flex flex-col gap-2">
              <ReviewView scrim={scrim} />
            </div>
          ) : set && round && m ? (
            <>
              <div style={{ gridArea: 'bans' }} className="flex flex-col gap-2">
                <ErrorText error={error} testId="scrim.error" />
                <BanBoard set={set} stage={scrim.stage} perms={perms} live={live} byName={byName} comps={comps.data ?? []} compsLoading={comps.isLoading} m={m} className="flex-1" />
              </div>
              <div style={{ gridArea: 'results' }} className="self-start">
                <ResultsColumn set={set} round={round} onRound={(n) => selectRound(set.id, n)} perms={perms} m={m} />
              </div>
              <div style={{ gridArea: 'main' }} className="flex min-w-0 flex-col gap-2 self-start">
                <OurLineup scrimId={scrim.id} set={set} round={round} perms={perms} live={live} byName={byName} fitsByShip={fitsByShip} pilots={options} warpLabels={scrimVocab.data?.warp_labels ?? []} linkScripts={compVocab.data?.link_scripts ?? []} m={m} />
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <TheirLineup set={set} round={round} perms={perms} live={live} byName={byName} archetypes={compVocab.data?.archetypes ?? []} m={m} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <RoundNotes set={set} round={round} onRound={(n) => selectRound(set.id, n)} onAdd={perms.edit ? m.addRound : undefined} onDelete={perms.manage ? m.deleteRound : undefined} perms={perms} live={live} save={(n, notes) => m.patchRound(n, { notes })} />
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div style={{ gridArea: 'bans' }}>
              <Panel title="Sets" testId="scrim.nosets">
                <ErrorText error={error} testId="scrim.error" />
                <Empty>
                  {perms.manage ? (
                    <span>
                      No sets yet.{' '}
                      <Button data-testid="scrim.nosets.new" variant="primary" disabled={sm.createSet.isPending} onClick={() => sm.createSet.mutate({ copy_previous: false, label: '' }, { onSuccess: (doc) => setSelectedSetId(doc.id) })}>
                        Start set 1
                      </Button>
                    </span>
                  ) : (
                    'No sets yet; a captain starts the first one.'
                  )}
                </Empty>
              </Panel>
            </div>
          )}
        </div>
        {set && round && view === 'board' && !shared ? (
          <div className="w-[290px] shrink-0">
            <FitsColumn round={round} perms={perms} />
          </div>
        ) : null}
      </div>
      {shareOpen ? <SharePanel scrimId={scrim.id} onClose={() => setShareOpen(false)} /> : null}
      {historyOpen ? (
        <HistoryDrawer
          scrimId={scrim.id}
          perms={perms}
          onClose={() => setHistoryOpen(false)}
          onRestoreSet={(setId) => sm.restoreSet.mutate({ setId }, { onSuccess: (doc) => setSelectedSetId(doc.id) })}
          onRestoreRound={(setId, roundNo) => sm.restoreRound.mutate({ setId, roundNo }, { onSuccess: (doc) => selectRound(doc.id, roundNo) })}
          restoring={sm.restoreSet.isPending || sm.restoreRound.isPending}
          error={sm.restoreSet.error ?? sm.restoreRound.error}
        />
      ) : null}
    </div>
  )
}

function StreamBadge({ status }: { status: StreamStatus }) {
  return (
    <Badge tone={status === 'live' ? 'ok' : status === 'offline' ? 'bad' : 'muted'} testId="scrim.stream.status">
      {status}
    </Badge>
  )
}

function Header({
  scrim,
  status,
  className,
  view,
  onView,
  onHistory,
  onShare,
  shared = false,
}: {
  scrim: SessionOut
  status: StreamStatus
  className?: string
  view: 'board' | 'review'
  onView: (v: 'board' | 'review') => void
  onHistory: () => void
  onShare: () => void
  /** Public share-link view: no RSVP, history, export or share controls. */
  shared?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const { patchScrim, archiveScrim } = useScrimMutations()
  if (editing) {
    return (
      <Panel title="Edit scrim" testId="scrim.edit">
        <SessionForm
          session={scrim}
          submitLabel="Save"
          pending={patchScrim.isPending}
          error={patchScrim.error}
          testPrefix="scrim.edit"
          onSubmit={(payload) => patchScrim.mutate({ id: scrim.id, body: payload }, { onSuccess: () => setEditing(false) })}
          onCancel={() => setEditing(false)}
        />
      </Panel>
    )
  }
  return (
    <Panel
      title={
        <span>
          <Link to="/scrims" className="text-accent">
            Scrims
          </Link>{' '}
          / {scrim.kind.replace('_', ' ')} <StreamBadge status={status} />
        </span>
      }
      testId="scrim.header"
      className={className}
      actions={
        <span className="flex flex-wrap items-center justify-end gap-1">
          <span className="flex rounded border border-line" role="tablist">
            <button type="button" role="tab" data-testid="scrim.header.view.board" onClick={() => onView('board')} className={clsx('rounded-l px-2 py-0.5 text-[11px]', view === 'board' ? 'bg-accent/15 font-medium text-accent' : 'text-muted hover:text-fg')}>
              Board
            </button>
            <button type="button" role="tab" data-testid="scrim.header.view.review" onClick={() => onView('review')} className={clsx('rounded-r px-2 py-0.5 text-[11px]', view === 'review' ? 'bg-accent/15 font-medium text-accent' : 'text-muted hover:text-fg')}>
              Review
            </button>
          </span>
          {shared ? (
            <Badge tone="info">shared view</Badge>
          ) : (
            <Button variant="ghost" className="h-6 px-1.5" data-testid="scrim.header.history" onClick={onHistory}>
              History
            </Button>
          )}
          {shared ? null : (
            <Link to="/scrims/$scrimId/me" params={{ scrimId: String(scrim.id) }} data-testid="scrim.header.me" className="inline-flex h-6 items-center rounded px-1.5 text-[12px] font-medium text-muted hover:bg-panel-2 hover:text-fg" title="your slot, big, for a second monitor">
              My card
            </Link>
          )}
          {shared ? null : (
          <a href={`/api/scrims/${scrim.id}/export.csv`} download data-testid="scrim.header.export" className="inline-flex h-6 items-center rounded border border-transparent px-1.5 text-[12px] font-medium text-muted hover:bg-panel-2 hover:text-fg" title="match log, one row per pilot per round">
            CSV
          </a>
          )}
          {scrim.can_manage ? (
          <>
            <Button variant="ghost" className="h-6 px-1.5" data-testid="scrim.header.share" onClick={onShare}>
              Share
            </Button>
            <Button variant="ghost" className="h-6 px-1.5" data-testid="scrim.header.edit" onClick={() => setEditing(true)}>
              Edit
            </Button>
            {!scrim.is_archived ? (
              <Button
                variant="ghost"
                className="h-6 px-1.5"
                data-testid="scrim.header.archive"
                onClick={() => {
                  const reason = window.prompt('Archive this scrim? Reason (kept in the audit log):')
                  if (reason !== null) archiveScrim.mutate({ id: scrim.id, reason })
                }}
              >
                Archive
              </Button>
            ) : null}
          </>
          ) : null}
        </span>
      }
    >
      <h1 className="text-base font-semibold" data-testid="scrim.header.title">
        {scrim.title}
      </h1>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
        <dt className="text-muted">when</dt>
        <dd>{whenAt(scrim.date)}</dd>
        <dt className="text-muted">opponent</dt>
        <dd data-testid="scrim.header.opponent">{scrim.opponent_name ?? <span className="text-muted">none yet</span>}</dd>
        <dt className="text-muted">system</dt>
        <dd>
          <Mono>{scrim.system_name || '—'}</Mono>
          {scrim.moveme_system ? <span className="text-muted"> · move-me {scrim.moveme_system}</span> : null}
        </dd>
        <dt className="text-muted">rules</dt>
        <dd>
          <Mono>{scrim.ruleset}</Mono> {scrim.stage ? <Badge tone="info">{scrim.stage}</Badge> : <Badge>no stage</Badge>}
        </dd>
        <dt className="text-muted">side</dt>
        <dd>{scrim.default_our_side ? `Team ${scrim.default_our_side}` : <span className="text-muted">per set</span>}</dd>
        {scrim.is_archived ? (
          <>
            <dt className="text-muted">status</dt>
            <dd>
              <Badge>archived</Badge>
            </dd>
          </>
        ) : null}
      </dl>
      {scrim.motd ? (
        <p className="mt-2 whitespace-pre-wrap rounded border border-line bg-bg p-2 text-[12px]" data-testid="scrim.header.motd">
          {scrim.motd}
        </p>
      ) : null}
      {shared ? null : (
        <div className="mt-2">
          <RsvpButtons scrim={scrim} testPrefix="scrim" />
        </div>
      )}
      <ErrorText error={archiveScrim.error} />
    </Panel>
  )
}

const RSVP_MARK: Record<string, string> = { yes: '\u2713', maybe: '?', no: '\u2717', none: '\u00b7' }

/** One line per pilot, as on the mockup: presence dot, RSVP mark, name, P/L/A toggles and a no-show action. */
function AttendanceRail({ scrim, online }: { scrim: SessionOut; online: Set<number> }) {
  const { setAttendance } = useScrimMutations()
  const [showMore, setShowMore] = useState(false)
  const listed = scrim.attendance.filter((a) => a.rsvp === 'yes' || a.rsvp === 'maybe' || a.attendance !== 'none')
  const folded = scrim.attendance.filter((a) => !listed.includes(a))
  const flying = scrim.attendance.filter((a) => a.attendance === 'present' || a.attendance === 'late').length
  const unable = folded.filter((a) => a.rsvp === 'no').length
  const set = (a: AttendanceOut) => (attendance: string, reason?: string) => setAttendance.mutate({ id: scrim.id, pilotId: a.pilot_id, attendance, reason })
  return (
    <Panel
      title="Attendance"
      testId="scrim.attendance"
      actions={
        <Mono className="text-[11px] text-muted" testId="scrim.attendance.tally">
          {flying} flying {'\u00b7'} {scrim.tally.yes} yes
        </Mono>
      }
    >
      <ErrorText error={setAttendance.error} testId="scrim.attendance.error" />
      <ul className="max-h-[250px] overflow-y-auto pr-1">
        {listed.map((a) => (
          <AttendanceRow key={a.pilot_id} row={a} scrim={scrim} online={a.user_id != null && online.has(a.user_id)} onSet={set(a)} />
        ))}
        {showMore ? folded.map((a) => <AttendanceRow key={a.pilot_id} row={a} scrim={scrim} online={a.user_id != null && online.has(a.user_id)} onSet={set(a)} />) : null}
      </ul>
      {folded.length ? (
        <button type="button" className="mt-1 w-full border-t border-dashed border-line py-1 text-left text-[11px] text-muted hover:text-fg" data-testid="scrim.attendance.more" onClick={() => setShowMore((v) => !v)}>
          {showMore ? '\u25be hide' : '\u25b8'} {folded.length} more: {unable} unable, {folded.length - unable} no answer
        </button>
      ) : null}
      <p className="mt-1 text-[11px] text-muted">{'P present \u00b7 L late \u00b7 A absent \u00b7 \u2717 no-show \u00b7 green dot = on this page'}</p>
    </Panel>
  )
}

function AttendanceRow({ row, scrim, online, onSet }: { row: AttendanceOut; scrim: SessionOut; online: boolean; onSet: (attendance: string, reason?: string) => void }) {
  const id = `scrim.attendance.row.${row.pilot_id}`
  const canSet = scrim.can_manage && !scrim.is_archived
  const toggle = (value: string, label: string, on: string) => (
    <button
      type="button"
      data-testid={`${id}.set.${value}`}
      title={value}
      disabled={!canSet}
      onClick={() => onSet(value)}
      className={clsx(
        'inline-flex h-[18px] w-[18px] items-center justify-center rounded-sm border text-[10px] font-semibold disabled:cursor-default',
        row.attendance === value ? on : 'border-line text-muted',
        canSet && row.attendance !== value && 'hover:border-muted hover:text-fg',
      )}
    >
      {label}
    </button>
  )
  return (
    <li data-testid={id} className={clsx('flex items-center gap-1.5 py-[3px] text-[12px]', row.is_me && 'text-accent')}>
      <i className={clsx('h-[7px] w-[7px] flex-none rounded-full', online ? 'bg-ok' : 'bg-line')} title={online ? 'on this page now' : 'not on this page'} data-testid={`${id}.online`} data-online={online ? 'true' : 'false'} />
      <Mono
        className={clsx('w-[14px] flex-none text-center', row.rsvp === 'yes' && 'text-ok', row.rsvp === 'maybe' && 'text-warn', row.rsvp === 'no' && 'text-bad', row.rsvp === 'none' && 'text-muted')}
        testId={`${id}.rsvp`}
      >
        {RSVP_MARK[row.rsvp] ?? row.rsvp}
      </Mono>
      <span className="min-w-0 flex-1 truncate" title={`${row.pilot_name}: ${RSVP_LABELS[row.rsvp]}${row.rsvp_reason ? ` (${row.rsvp_reason})` : ''}`}>
        {row.pilot_name}
        {row.rsvp_reason ? (
          <span className="text-muted" data-testid={`${id}.reason`}>
            {' \u00b7 "'}{row.rsvp_reason}{'"'}
          </span>
        ) : null}
      </span>
      {row.attendance === 'no_show' ? (
        <Badge tone="bad" testId={`${id}.removed`}>
          <span title={row.removed_reason}>no-show</span>
        </Badge>
      ) : (
        <span className="flex flex-none gap-0.5">
          {toggle('present', 'P', 'border-ok bg-ok/20 text-ok')}
          {toggle('late', 'L', 'border-warn bg-warn/20 text-warn')}
          {toggle('absent', 'A', 'border-bad bg-bad/20 text-bad')}
          {canSet ? (
            <button
              type="button"
              data-testid={`${id}.set.no_show`}
              title="remove as no-show"
              className="inline-flex h-[18px] w-[18px] items-center justify-center rounded-sm border border-line text-[10px] text-bad hover:border-bad"
              onClick={() => {
                const reason = window.prompt(`Remove ${row.pilot_name} as a no-show. Reason (kept in the audit log):`)
                if (reason !== null) onSet('no_show', reason)
              }}
            >
              {'\u2717'}
            </button>
          ) : null}
        </span>
      )}
    </li>
  )
}
