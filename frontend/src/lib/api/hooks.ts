import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  unwrap,
  type CompCreateIn,
  type CompPatchIn,
  type FitCreateIn,
  type FitPatchIn,
  type MemberPatch,
  type OpponentIn,
  type OpponentPatchIn,
  type PilotIn,
  type PilotPatchIn,
  type Role,
  type AssignmentPatchIn,
  type SessionCreateIn,
  type SessionOut,
  type SessionPatchIn,
  type SetDoc,
  type SetPatchIn,
  type TeamPatch,
} from './client'

export const keys = {
  me: ['me'] as const,
  health: ['health'] as const,
  members: ['team', 'members'] as const,
  invites: ['team', 'invites'] as const,
  rules: ['team', 'admission-rules'] as const,
  audit: (filters: Record<string, string | number | undefined>) => ['audit', filters] as const,
  rulesets: ['rulesets'] as const,
  ships: (code: string) => ['rulesets', code, 'ships'] as const,
  fits: (filters: FitFilters) => ['fits', 'list', filters] as const,
  fit: (id: number) => ['fits', 'one', id] as const,
  legality: (id: number, code: string, flagship: boolean) => ['fits', 'one', id, 'legality', code, flagship] as const,
  comps: (filters: CompFilters) => ['comps', 'list', filters] as const,
  comp: (id: number) => ['comps', 'one', id] as const,
  compVocab: ['comps', 'vocab'] as const,
  scrims: (when: ScrimWhen) => ['scrims', 'list', when] as const,
  scrim: (id: number) => ['scrims', 'one', id] as const,
  scrimVocab: ['scrims', 'vocab'] as const,
  pilots: (status?: string) => ['pilots', status ?? ''] as const,
  opponents: ['opponents'] as const,
}

export type ScrimWhen = 'upcoming' | 'past' | 'all'

export type CompFilters = { ruleset?: string; status?: string; archetype?: number; q?: string; banned?: string }

export type FitFilters = { ship?: number; status?: string; q?: string }

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: async () => unwrap(await api.GET('/api/me')), staleTime: 60_000 })
}

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: async () => unwrap(await api.GET('/api/health')), staleTime: 30_000 })
}

export function useMembers(enabled = true) {
  return useQuery({ queryKey: keys.members, queryFn: async () => unwrap(await api.GET('/api/team/members')), enabled })
}

export function useInvites(enabled = true) {
  return useQuery({ queryKey: keys.invites, queryFn: async () => unwrap(await api.GET('/api/team/invites')), enabled })
}

export function useAdmissionRules(enabled = true) {
  return useQuery({ queryKey: keys.rules, queryFn: async () => unwrap(await api.GET('/api/team/admission-rules')), enabled })
}

export function useAudit(filters: { action?: string; limit: number; offset: number }) {
  return useQuery({
    queryKey: keys.audit(filters),
    queryFn: async () => unwrap(await api.GET('/api/audit', { params: { query: filters } })),
  })
}

export function useRulesets() {
  return useQuery({ queryKey: keys.rulesets, queryFn: async () => unwrap(await api.GET('/api/rulesets')) })
}

export function useRulesetShips(code: string) {
  return useQuery({
    queryKey: keys.ships(code),
    queryFn: async () => unwrap(await api.GET('/api/rulesets/{code}/ships', { params: { path: { code } } })),
    staleTime: Infinity,
    enabled: Boolean(code),
  })
}

export function useFits(filters: FitFilters) {
  return useQuery({
    queryKey: keys.fits(filters),
    queryFn: async () => unwrap(await api.GET('/api/fits', { params: { query: filters } })),
  })
}

export function useFit(id: number) {
  return useQuery({
    queryKey: keys.fit(id),
    queryFn: async () => unwrap(await api.GET('/api/fits/{fit_id}', { params: { path: { fit_id: id } } })),
  })
}

export function useFitLegality(id: number, code: string | undefined, flagship: boolean) {
  return useQuery({
    queryKey: keys.legality(id, code ?? '', flagship),
    queryFn: async () =>
      unwrap(await api.GET('/api/fits/{fit_id}/legality', { params: { path: { fit_id: id }, query: code ? { ruleset: code, flagship } : { flagship } } })),
  })
}

export function useFitMutations() {
  const qc = useQueryClient()
  const refreshFits = () => qc.invalidateQueries({ queryKey: ['fits'] })
  return {
    parseFit: useMutation({
      mutationFn: async (body: { eft_text: string; pyfa_summary: string }) => unwrap(await api.POST('/api/fits/parse', { body })),
    }),
    createFit: useMutation({
      mutationFn: async (body: FitCreateIn) => unwrap(await api.POST('/api/fits', { body })),
      onSuccess: refreshFits,
    }),
    patchFit: useMutation({
      mutationFn: async (vars: { id: number; body: FitPatchIn }) =>
        unwrap(await api.PATCH('/api/fits/{fit_id}', { params: { path: { fit_id: vars.id } }, body: vars.body })),
      onSuccess: refreshFits,
    }),
  }
}

export function useComps(filters: CompFilters, enabled = true) {
  return useQuery({
    queryKey: keys.comps(filters),
    queryFn: async () => unwrap(await api.GET('/api/comps', { params: { query: filters } })),
    enabled,
  })
}

export function useComp(id: number) {
  return useQuery({
    queryKey: keys.comp(id),
    queryFn: async () => unwrap(await api.GET('/api/comps/{comp_id}', { params: { path: { comp_id: id } } })),
  })
}

export function useCompVocab() {
  return useQuery({ queryKey: keys.compVocab, queryFn: async () => unwrap(await api.GET('/api/comps/vocab')), staleTime: 300_000 })
}

export function useCompMutations() {
  const qc = useQueryClient()
  const refreshComps = () => qc.invalidateQueries({ queryKey: ['comps'] })
  return {
    createComp: useMutation({
      mutationFn: async (body: CompCreateIn) => unwrap(await api.POST('/api/comps', { body })),
      onSuccess: refreshComps,
    }),
    patchComp: useMutation({
      mutationFn: async (vars: { id: number; body: CompPatchIn }) =>
        unwrap(await api.PATCH('/api/comps/{comp_id}', { params: { path: { comp_id: vars.id } }, body: vars.body })),
      onSuccess: refreshComps,
    }),
    cloneComp: useMutation({
      mutationFn: async (vars: { id: number; name?: string | null; ruleset?: string | null }) =>
        unwrap(await api.POST('/api/comps/{comp_id}/clone', { params: { path: { comp_id: vars.id } }, body: { name: vars.name ?? null, ruleset: vars.ruleset ?? null } })),
      onSuccess: refreshComps,
    }),
    createArchetype: useMutation({
      mutationFn: async (body: { name: string; description: string; sort_order: number }) => unwrap(await api.POST('/api/comps/archetypes', { body })),
      onSuccess: refreshComps,
    }),
  }
}

/** Mutations invalidate the lists they touch so every page refreshes without wiring. */
export function useTeamMutations() {
  const qc = useQueryClient()
  const refresh = (...groups: readonly (readonly string[])[]) => groups.forEach((k) => qc.invalidateQueries({ queryKey: k }))
  return {
    patchTeam: useMutation({
      mutationFn: async (body: TeamPatch) => unwrap(await api.PATCH('/api/team', { body })),
      onSuccess: () => {
        refresh(keys.me)
        qc.invalidateQueries({ queryKey: ['comps'] })
        qc.invalidateQueries({ queryKey: ['fits'] })
      },
    }),
    patchMember: useMutation({
      mutationFn: async (vars: { userId: number; body: MemberPatch }) =>
        unwrap(await api.PATCH('/api/team/members/{user_id}', { params: { path: { user_id: vars.userId } }, body: vars.body })),
      onSuccess: () => refresh(keys.members, keys.me),
    }),
    removeMember: useMutation({
      mutationFn: async (vars: { userId: number; reason: string }) =>
        unwrap(await api.DELETE('/api/team/members/{user_id}', { params: { path: { user_id: vars.userId } }, body: { reason: vars.reason } })),
      onSuccess: () => refresh(keys.members),
    }),
    createInvite: useMutation({
      mutationFn: async (body: { role: Role; uses: number; expires_in_hours: number; note: string }) =>
        unwrap(await api.POST('/api/team/invites', { body })),
      onSuccess: () => refresh(keys.invites),
    }),
    revokeInvite: useMutation({
      mutationFn: async (id: number) => unwrap(await api.DELETE('/api/team/invites/{invite_id}', { params: { path: { invite_id: id } } })),
      onSuccess: () => refresh(keys.invites),
    }),
    createRule: useMutation({
      mutationFn: async (body: { kind: 'corporation' | 'alliance'; entity_id: number; entity_name: string; default_role: Role; enabled: boolean }) =>
        unwrap(await api.POST('/api/team/admission-rules', { body })),
      onSuccess: () => refresh(keys.rules),
    }),
    patchRule: useMutation({
      mutationFn: async (vars: { id: number; enabled: boolean }) =>
        unwrap(await api.PATCH('/api/team/admission-rules/{rule_id}', { params: { path: { rule_id: vars.id } }, body: { enabled: vars.enabled } })),
      onSuccess: () => refresh(keys.rules),
    }),
    deleteRule: useMutation({
      mutationFn: async (id: number) => unwrap(await api.DELETE('/api/team/admission-rules/{rule_id}', { params: { path: { rule_id: id } } })),
      onSuccess: () => refresh(keys.rules),
    }),
  }
}

export function useScrims(when: ScrimWhen, enabled = true) {
  return useQuery({
    queryKey: keys.scrims(when),
    queryFn: async () => unwrap(await api.GET('/api/scrims', { params: { query: { when } } })),
    enabled,
  })
}

export function useScrim(id: number, enabled = true) {
  return useQuery({
    queryKey: keys.scrim(id),
    queryFn: async () => unwrap(await api.GET('/api/scrims/{session_id}', { params: { path: { session_id: id } } })),
    enabled,
  })
}

export function useScrimVocab(enabled = true) {
  return useQuery({ queryKey: keys.scrimVocab, queryFn: async () => unwrap(await api.GET('/api/scrims/vocab')), staleTime: 300_000, enabled })
}

export function usePilots(status?: string, enabled = true) {
  return useQuery({
    queryKey: keys.pilots(status),
    queryFn: async () => unwrap(await api.GET('/api/pilots', { params: { query: status ? { status } : {} } })),
    enabled,
  })
}

export function useOpponents(enabled = true) {
  return useQuery({ queryKey: keys.opponents, queryFn: async () => unwrap(await api.GET('/api/opponents')), enabled })
}

/** Every scrim write answers with the full session, which lands straight in the cache; lists refresh behind it. */
export function useScrimMutations() {
  const qc = useQueryClient()
  const landed = (session: SessionOut) => {
    qc.setQueryData(keys.scrim(session.id), session)
    qc.invalidateQueries({ queryKey: ['scrims', 'list'] })
  }
  const path = (id: number) => ({ params: { path: { session_id: id } } })
  return {
    createScrim: useMutation({
      mutationFn: async (body: SessionCreateIn) => unwrap(await api.POST('/api/scrims', { body })),
      onSuccess: landed,
    }),
    patchScrim: useMutation({
      mutationFn: async (vars: { id: number; body: SessionPatchIn }) => unwrap(await api.PATCH('/api/scrims/{session_id}', { ...path(vars.id), body: vars.body })),
      onSuccess: landed,
    }),
    archiveScrim: useMutation({
      mutationFn: async (vars: { id: number; reason: string }) =>
        unwrap(await api.POST('/api/scrims/{session_id}/archive', { ...path(vars.id), body: { reason: vars.reason } })),
      onSuccess: landed,
    }),
    rsvp: useMutation({
      mutationFn: async (vars: { id: number; rsvp: string; reason?: string }) =>
        unwrap(await api.PUT('/api/scrims/{session_id}/rsvp', { ...path(vars.id), body: { rsvp: vars.rsvp, reason: vars.reason ?? '' } })),
      onSuccess: landed,
    }),
    setAttendance: useMutation({
      mutationFn: async (vars: { id: number; pilotId: number; attendance: string; reason?: string }) =>
        unwrap(
          await api.PATCH('/api/scrims/{session_id}/attendance/{pilot_id}', {
            params: { path: { session_id: vars.id, pilot_id: vars.pilotId } },
            body: { attendance: vars.attendance, reason: vars.reason ?? '' },
          }),
        ),
      onSuccess: landed,
    }),
  }
}

export function useRosterMutations() {
  const qc = useQueryClient()
  const refreshPilots = () => qc.invalidateQueries({ queryKey: ['pilots'] })
  const refreshOpponents = () => qc.invalidateQueries({ queryKey: keys.opponents })
  return {
    createPilot: useMutation({
      mutationFn: async (body: PilotIn) => unwrap(await api.POST('/api/pilots', { body })),
      onSuccess: refreshPilots,
    }),
    patchPilot: useMutation({
      mutationFn: async (vars: { id: number; body: PilotPatchIn }) =>
        unwrap(await api.PATCH('/api/pilots/{pilot_id}', { params: { path: { pilot_id: vars.id } }, body: vars.body })),
      onSuccess: refreshPilots,
    }),
    createOpponent: useMutation({
      mutationFn: async (body: OpponentIn) => unwrap(await api.POST('/api/opponents', { body })),
      onSuccess: refreshOpponents,
    }),
    patchOpponent: useMutation({
      mutationFn: async (vars: { id: number; body: OpponentPatchIn }) =>
        unwrap(await api.PATCH('/api/opponents/{opponent_id}', { params: { path: { opponent_id: vars.id } }, body: vars.body })),
      onSuccess: refreshOpponents,
    }),
  }
}

/** Replace (or add) one set document inside the cached session; the stream and every set write use this. */
export function upsertSet(session: SessionOut, doc: SetDoc): SessionOut {
  const idx = session.sets.findIndex((s) => s.id === doc.id)
  const sets = idx === -1 ? [...session.sets, doc].sort((a, b) => a.index - b.index) : session.sets.map((s) => (s.id === doc.id ? doc : s))
  return { ...session, sets }
}

export function useSetMutations(sessionId: number) {
  const qc = useQueryClient()
  const landed = (doc: SetDoc) => qc.setQueryData<SessionOut>(keys.scrim(sessionId), (old) => (old ? upsertSet(old, doc) : old))
  const removed = (setId: number) =>
    qc.setQueryData<SessionOut>(keys.scrim(sessionId), (old) => (old ? { ...old, sets: old.sets.filter((s) => s.id !== setId) } : old))
  return {
    createSet: useMutation({
      mutationFn: async (body: { copy_previous: boolean; label: string }) => unwrap(await api.POST('/api/scrims/{session_id}/sets', { params: { path: { session_id: sessionId } }, body })),
      onSuccess: landed,
    }),
    patchSet: useMutation({
      mutationFn: async (vars: { setId: number; body: SetPatchIn }) =>
        unwrap(await api.PATCH('/api/scrims/{session_id}/sets/{set_id}', { params: { path: { session_id: sessionId, set_id: vars.setId } }, body: vars.body })),
      onSuccess: landed,
    }),
    deleteSet: useMutation({
      mutationFn: async (vars: { setId: number; reason: string }) => {
        unwrap(await api.DELETE('/api/scrims/{session_id}/sets/{set_id}', { params: { path: { session_id: sessionId, set_id: vars.setId } }, body: { reason: vars.reason } }))
        return vars.setId
      },
      onSuccess: removed,
    }),
    putBan: useMutation({
      mutationFn: async (vars: { setId: number; side: string; kind: string; index: number; type_id: number | null; in_effect_from_round?: number }) =>
        unwrap(
          await api.POST('/api/scrims/{session_id}/sets/{set_id}/bans', {
            params: { path: { session_id: sessionId, set_id: vars.setId } },
            body: { side: vars.side, kind: vars.kind, index: vars.index, type_id: vars.type_id, in_effect_from_round: vars.in_effect_from_round ?? 1 },
          }),
        ),
      onSuccess: landed,
    }),
    addRound: useMutation({
      mutationFn: async (vars: { setId: number }) => unwrap(await api.POST('/api/scrims/{session_id}/sets/{set_id}/rounds', { params: { path: { session_id: sessionId, set_id: vars.setId } } })),
      onSuccess: landed,
    }),
    deleteRound: useMutation({
      mutationFn: async (vars: { setId: number; roundNo: number }) =>
        unwrap(await api.DELETE('/api/scrims/{session_id}/sets/{set_id}/rounds/{round_no}', { params: { path: { session_id: sessionId, set_id: vars.setId, round_no: vars.roundNo } } })),
      onSuccess: landed,
    }),
    patchRound: useMutation({
      mutationFn: async (vars: { setId: number; roundNo: number; body: { outcome?: string | null; notes?: string | null } }) =>
        unwrap(await api.PATCH('/api/scrims/{session_id}/sets/{set_id}/rounds/{round_no}', { params: { path: { session_id: sessionId, set_id: vars.setId, round_no: vars.roundNo } }, body: vars.body })),
      onSuccess: landed,
    }),
    patchAssignment: useMutation({
      mutationFn: async (vars: { setId: number; roundNo: number; side: 'US' | 'OPP'; slotNo: number; body: AssignmentPatchIn }) =>
        unwrap(
          await api.PATCH('/api/scrims/{session_id}/sets/{set_id}/rounds/{round_no}/{side}/{slot_no}', {
            params: { path: { session_id: sessionId, set_id: vars.setId, round_no: vars.roundNo, side: vars.side, slot_no: vars.slotNo } },
            body: vars.body,
          }),
        ),
      onSuccess: landed,
    }),
    pasteOpp: useMutation({
      mutationFn: async (vars: { setId: number; roundNo: number; text: string }) =>
        unwrap(
          await api.POST('/api/scrims/{session_id}/sets/{set_id}/rounds/{round_no}/opp-lineup', {
            params: { path: { session_id: sessionId, set_id: vars.setId, round_no: vars.roundNo } },
            body: { text: vars.text },
          }),
        ),
      onSuccess: (out) => landed(out.set),
    }),
  }
}

export async function sendPresence(sessionId: number, focus: string | null) {
  return unwrap(await api.POST('/api/scrims/{session_id}/presence', { params: { path: { session_id: sessionId } }, body: { focus } }))
}

export function leavePresence(sessionId: number) {
  void api.DELETE('/api/scrims/{session_id}/presence', { params: { path: { session_id: sessionId } } })
}
