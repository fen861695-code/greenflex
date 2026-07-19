const dateTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTime.format(new Date(value)) : '—'
}

export function formatNumber(value: string | number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  return Number.isFinite(numeric)
    ? numeric.toLocaleString('zh-CN', { maximumFractionDigits: digits })
    : '—'
}

export function formatRmb(value: string | null | undefined): string {
  return value === null || value === undefined ? '—' : `¥${formatNumber(value, 6)}`
}

export function formatStatus(status: string): string {
  const labels: Record<string, string> = {
    queued: '排队中',
    scheduled: '已计划',
    running: '执行中',
    succeeded: '已完成',
    partial_success: '部分成功',
    failed: '失败',
    cancelled: '已取消',
    pending: '待执行',
  }
  return labels[status] ?? status
}

export function statusTone(status: string): string {
  if (status === 'succeeded') return 'success'
  if (status === 'partial_success' || status === 'scheduled') return 'warning'
  if (status === 'failed' || status === 'cancelled') return 'danger'
  if (status === 'running') return 'measured'
  return 'neutral'
}
