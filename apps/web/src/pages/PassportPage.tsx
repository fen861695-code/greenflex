import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Copy, FileCheck2, ShieldCheck } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { api, apiMessage } from '../api/client'
import { C2PABadge } from '../components/C2PABadge'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { formatDateTime, formatNumber, formatRmb } from '../utils/format'

export function PassportPage() {
  const { id = '' } = useParams()
  const passport = useQuery({
    queryKey: ['passport', id],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/orders/{order_id}/passport', { params: { path: { order_id: id } } })
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })
  if (passport.isLoading) return <main className="page"><LoadingState label="核验 Token Passport" /></main>
  if (passport.isError || !passport.data) return <main className="page"><ErrorState message={apiMessage(passport.error)} /></main>
  const payload = passport.data.payload
  const grade = read(payload, 'green_grade', 'grade')
  const actualMicroRmb = readNumber(payload, 'bill', 'actual_micro_rmb')
  return (
    <main className="page passport-page">
      <PageHeader
        eyebrow="Token Passport"
        title={`仿真绿色等级 ${typeof grade === 'string' ? grade : '—'}`}
        actions={<ProvenanceBadge value="simulated" detail="该等级不是官方认证" />}
      />
      <div className="passport-identity">
        <div className="grade-mark">{typeof grade === 'string' ? grade : '—'}</div>
        <div><span>凭证 ID</span><strong>{passport.data.passport_id}</strong><small>签发于 {formatDateTime(passport.data.created_at)}</small></div>
        <FileCheck2 aria-hidden="true" />
      </div>
      <div className="passport-grid">
        <section>
          <div className="section-heading compact"><h2>使用量与模型</h2><ProvenanceBadge value="measured" /></div>
          <dl className="detail-list">
            <div><dt>模型</dt><dd>{stringValue(read(payload, 'model', 'runtime_name'))}</dd></div>
            <div><dt>输入 Token</dt><dd>{formatNumber(readNumber(payload, 'usage', 'input_tokens'), 0)}</dd></div>
            <div><dt>输出 Token</dt><dd>{formatNumber(readNumber(payload, 'usage', 'output_tokens'), 0)}</dd></div>
            <div><dt>模型摘要</dt><dd className="hash-value">{stringValue(read(payload, 'model', 'digest'))}</dd></div>
          </dl>
        </section>
        <section>
          <div className="section-heading compact"><h2>能源与碳</h2><ProvenanceBadge value="estimated" /></div>
          <dl className="detail-list">
            <div><dt>GPU 总能耗</dt><dd>{microToUnit(readNumber(payload, 'gpu_energy', 'gross_micro_wh'), 1_000_000)} Wh</dd></div>
            <div><dt>GPU 增量能耗</dt><dd>{microToUnit(readNumber(payload, 'gpu_energy', 'incremental_micro_wh'), 1_000_000)} Wh</dd></div>
            <div><dt>机房能耗</dt><dd>{microToUnit(readNumber(payload, 'facility_energy', 'micro_wh'), 1_000_000)} Wh</dd></div>
            <div><dt>位置法碳排</dt><dd>{microToUnit(readNumber(payload, 'location_carbon', 'micro_g_co2e'), 1_000_000)} gCO₂e</dd></div>
          </dl>
        </section>
        <section>
          <div className="section-heading compact"><h2>GreenBill</h2><ProvenanceBadge value="simulated" /></div>
          <dl className="detail-list">
            <div><dt>实际结算</dt><dd>{formatRmb(actualMicroRmb === null ? null : String(actualMicroRmb / 1_000_000))}</dd></div>
            <div><dt>弹性折扣</dt><dd>{formatNumber(readNumber(payload, 'bill', 'discount_bps') === null ? null : Number(readNumber(payload, 'bill', 'discount_bps')) / 100, 2)}%</dd></div>
            <div><dt>VPP 返利</dt><dd>¥0.000000</dd></div>
            <div><dt>价格版本</dt><dd>{stringValue(read(payload, 'bill', 'pricing_version'))}</dd></div>
          </dl>
        </section>
        <section>
          <div className="section-heading compact"><h2>声明边界</h2><ShieldCheck aria-hidden="true" /></div>
          <ul className="claim-list"><li><CheckCircle2 />不包含原始提示词和输出</li><li><CheckCircle2 />不主张零碳</li><li><CheckCircle2 />不构成官方认证</li><li><CheckCircle2 />无市场法绿电声明</li></ul>
        </section>
      </div>
      <section className="audit-proof">
        <div><span>Passport SHA-256</span><code>{passport.data.payload_sha256}</code></div>
        <button className="icon-button" title="复制校验值" onClick={() => void navigator.clipboard.writeText(passport.data.payload_sha256)}><Copy aria-hidden="true" /></button>
      </section>

      <section className="c2pa-section">
        <div className="section-heading"><h2>C2PA 内容凭证</h2><ProvenanceBadge value="simulated" detail="C2PA为仿真实现" /></div>
        <C2PABadge passportId={passport.data.passport_id} />
      </section>

      <Link className="button secondary" to={`/orders/${passport.data.order_id}`}>返回订单</Link>
    </main>
  )
}

function read(value: Record<string, unknown>, section: string, field: string): unknown {
  const nested = value[section]
  return typeof nested === 'object' && nested !== null && field in nested
    ? (nested as Record<string, unknown>)[field]
    : null
}

function readNumber(value: Record<string, unknown>, section: string, field: string): number | null {
  const candidate = read(value, section, field)
  return typeof candidate === 'number' ? candidate : null
}

function stringValue(value: unknown): string {
  return typeof value === 'string' && value.length > 0 ? value : '—'
}

function microToUnit(value: number | null, divisor: number): string {
  return value === null ? '—' : formatNumber(value / divisor, 6)
}
