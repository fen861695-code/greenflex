import { describe, expect, it } from 'vitest'

import { formatDateTime, formatNumber, formatRmb, formatStatus, statusTone } from './format'

describe('display formatting', () => {
  it('formats empty and numeric values deterministically', () => {
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber('1.23456', 2)).toBe('1.23')
    expect(formatNumber('invalid')).toBe('—')
    expect(formatRmb('0.123456')).toBe('¥0.123456')
  })

  it('formats status labels and tones', () => {
    expect(formatStatus('partial_success')).toBe('部分成功')
    expect(formatStatus('custom')).toBe('custom')
    expect(statusTone('succeeded')).toBe('success')
    expect(statusTone('failed')).toBe('danger')
    expect(statusTone('running')).toBe('measured')
    expect(statusTone('queued')).toBe('neutral')
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime('2026-07-19T09:00:00Z')).not.toBe('—')
  })
})
