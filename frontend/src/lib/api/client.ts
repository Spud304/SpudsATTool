import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

export const api = createClient<paths>({ baseUrl: '', credentials: 'same-origin' })

export type RulesetOut = components['schemas']['RulesetOut']
export type ShipOut = components['schemas']['ShipOut']
export type EvaluateIn = components['schemas']['EvaluateIn']
export type EvaluateOut = components['schemas']['EvaluateOut']
export type SlotIn = components['schemas']['SlotIn']
export type BanIn = components['schemas']['BanIn']

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `API error ${status}`)
    this.status = status
  }
}

/** Unwrap an openapi-fetch result, throwing ApiError on non-2xx. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (!result.response.ok || result.data === undefined) {
    const detail =
      result.error && typeof result.error === 'object' && 'detail' in result.error
        ? (result.error as { detail: unknown }).detail
        : result.error
    throw new ApiError(result.response.status, detail)
  }
  return result.data
}
