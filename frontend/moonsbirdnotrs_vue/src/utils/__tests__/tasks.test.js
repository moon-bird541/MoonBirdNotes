import { describe, expect, it } from 'vitest'

import {
  formatTaskRange,
  fromLocalInputValue,
  groupTasksBySegment,
  resolveUrgencyLabel,
  resolveUrgencyTone,
  toLocalInputValue,
} from '../tasks'

describe('groupTasksBySegment', () => {
  it('splits tasks into todo and project groups', () => {
    const groups = groupTasksBySegment([
      { id: 1, segment: 'todo' },
      { id: 2, segment: 'project' },
      { id: 3, segment: 'todo' },
    ])

    expect(groups.todo.map((task) => task.id)).toEqual([1, 3])
    expect(groups.project.map((task) => task.id)).toEqual([2])
  })

  it('treats unknown segment as project', () => {
    const groups = groupTasksBySegment([{ id: 1 }])

    expect(groups.todo).toHaveLength(0)
    expect(groups.project.map((task) => task.id)).toEqual([1])
  })
})

describe('urgency helpers', () => {
  it('maps urgency value to tone', () => {
    expect(resolveUrgencyTone(1)).toBe('low')
    expect(resolveUrgencyTone(4)).toBe('urgent')
  })

  it('falls back to low for unknown urgency', () => {
    expect(resolveUrgencyTone(99)).toBe('low')
  })

  it('prefers server-provided display label', () => {
    expect(resolveUrgencyLabel({ urgency: 3, urgency_display: '高' })).toBe('高')
    expect(resolveUrgencyLabel({ urgency: 3 })).toBe('高')
  })
})

describe('time helpers', () => {
  it('converts datetime to local input value', () => {
    const value = new Date(2026, 10, 2, 14, 5)

    expect(toLocalInputValue(value)).toBe('2026-11-02T14:05')
  })

  it('returns empty string for missing time', () => {
    expect(toLocalInputValue(null)).toBe('')
    expect(toLocalInputValue('not-a-date')).toBe('')
  })

  it('round-trips local input value through ISO', () => {
    const iso = fromLocalInputValue('2026-11-02T14:05')

    expect(new Date(iso).getTime()).toBe(new Date(2026, 10, 2, 14, 5).getTime())
    expect(toLocalInputValue(iso)).toBe('2026-11-02T14:05')
  })

  it('describes a task without time as undated', () => {
    expect(formatTaskRange({ has_time: false })).toBe('时间未定')
    expect(formatTaskRange({ has_time: true, start_at: null, end_at: null })).toContain('时间未定')
  })
})
