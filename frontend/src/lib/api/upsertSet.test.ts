import { describe, expect, it } from 'vitest'
import type { SessionOut, SetDoc } from './client'
import { upsertSet } from './hooks'

const set = (id: number, seq: number, label = ''): SetDoc => ({ id, index: id, seq, label }) as SetDoc
const session = (eventSeq: number, sets: SetDoc[]): SessionOut => ({ event_seq: eventSeq, sets }) as SessionOut

describe('upsertSet', () => {
  it('replaces a set with a newer copy', () => {
    const out = upsertSet(session(5, [set(1, 3, 'old')]), set(1, 6, 'new'))
    expect(out.sets[0].label).toBe('new')
  })

  it('drops a copy older than the one held', () => {
    const held = session(7, [set(1, 7, 'from stream')])
    expect(upsertSet(held, set(1, 6, 'slow reply'))).toBe(held)
  })

  it('adds a set the stream has not reached yet', () => {
    const out = upsertSet(session(4, [set(1, 3)]), set(2, 5))
    expect(out.sets.map((s) => s.id)).toEqual([1, 2])
  })

  it('does not bring back a set deleted after this copy was made', () => {
    const held = session(9, [set(1, 3)])
    expect(upsertSet(held, set(2, 8))).toBe(held)
  })
})
