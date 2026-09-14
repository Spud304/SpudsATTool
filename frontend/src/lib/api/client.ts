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
export type TeamPatch = Schemas['TeamPatch']
export type MemberOut = Schemas['MemberOut']
export type MemberPatch = Schemas['MemberPatch']
export type InviteOut = Schemas['InviteOut']
export type AdmissionRuleOut = Schemas['AdmissionRuleOut']
export type AuditOut = Schemas['AuditOut']
export type Role = Schemas['Role']

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
