import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './schema'

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

// Session-cookie auth: Django needs the CSRF token on every unsafe method.
const csrf: Middleware = {
  async onRequest({ request }) {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
      const token = readCookie('csrftoken')
      if (token) request.headers.set('X-CSRFToken', token)
    }
    return request
  },
}

export const api = createClient<paths>({ baseUrl: '', credentials: 'same-origin' })
api.use(csrf)

export type Schemas = components['schemas']
export type RulesetOut = Schemas['RulesetOut']
export type ShipOut = Schemas['ShipOut']
export type EvaluateIn = Schemas['EvaluateIn']
export type EvaluateOut = Schemas['EvaluateOut']
export type SlotIn = Schemas['SlotIn']
export type BanIn = Schemas['BanIn']
export type MeOut = Schemas['MeOut']
export type FitOut = Schemas['FitOut']
export type FitSummaryOut = Schemas['FitSummaryOut']
export type FitCreateIn = Schemas['FitCreateIn']
export type FitPatchIn = Schemas['FitPatchIn']
export type ParseOut = Schemas['ParseOut']
export type LegalityOut = Schemas['LegalityOut']
export type CompOut = Schemas['CompOut']
export type CompSummaryOut = Schemas['CompSummaryOut']
export type CompSlotOut = Schemas['CompSlotOut']
export type CompSlotIn = Schemas['CompSlotIn']
export type CompCreateIn = Schemas['CompCreateIn']
export type CompPatchIn = Schemas['CompPatchIn']
export type CompVocabOut = Schemas['CompVocabOut']
export type ArchetypeOut = Schemas['ArchetypeOut']
export type LinkScriptOut = Schemas['LinkScriptOut']
export type TeamPatch = Schemas['TeamPatch']
export type MemberOut = Schemas['MemberOut']
export type MemberPatch = Schemas['MemberPatch']
export type InviteOut = Schemas['InviteOut']
export type AdmissionRuleOut = Schemas['AdmissionRuleOut']
export type AuditOut = Schemas['AuditOut']
export type RoleOut = Schemas['RoleOut']
export type RolesOut = Schemas['RolesOut']
export type RoleIn = Schemas['RoleIn']
export type RolePatch = Schemas['RolePatch']
export type ScratchpadOut = Schemas['ScratchpadOut']
export type ScratchpadIn = Schemas['ScratchpadIn']
export type SessionOut = Schemas['SessionOut']
export type SessionSummaryOut = Schemas['SessionSummaryOut']
export type AttendanceOut = Schemas['AttendanceOut']
export type SessionCreateIn = Schemas['SessionCreateIn']
export type SessionPatchIn = Schemas['SessionPatchIn']
export type ScrimVocabOut = Schemas['VocabOut']
export type PilotOut = Schemas['PilotOut']
export type PilotIn = Schemas['PilotIn']
export type PilotPatchIn = Schemas['PilotPatchIn']
export type OpponentOut = Schemas['OpponentOut']
export type OpponentIn = Schemas['OpponentIn']
export type OpponentPatchIn = Schemas['OpponentPatchIn']
export type SetDoc = Schemas['SetDocOut']
export type RoundDoc = Schemas['RoundDocOut']
export type SideDoc = Schemas['SideDocOut']
export type SlotDoc = Schemas['SlotDocOut']
export type BanChip = Schemas['BanChipOut']
export type ScoreDoc = Schemas['ScoreOut']
export type SetPatchIn = Schemas['SetPatchIn']
export type AssignmentPatchIn = Schemas['AssignmentPatchIn']
export type ViewerOut = Schemas['ViewerOut']
export type HistoryOut = Schemas['HistoryOut']
export type ShareLinkOut = Schemas['ShareLinkOut']
export type HistoryEntryOut = Schemas['HistoryEntryOut']
export type DeletedSetOut = Schemas['DeletedSetOut']
export type DeletedRoundOut = Schemas['DeletedRoundOut']

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `API error ${status}`)
    this.status = status
  }
}

/** Unwrap an openapi-fetch result, throwing ApiError on non-2xx. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (!result.response.ok) {
    const detail =
      result.error && typeof result.error === 'object' && 'detail' in result.error
        ? (result.error as { detail: unknown }).detail
        : result.error
    throw new ApiError(result.response.status, detail)
  }
  return result.data as T
}
