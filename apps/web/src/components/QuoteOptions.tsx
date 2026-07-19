import { ArrowRight, Clock3, Gauge, Leaf, WalletCards } from 'lucide-react'

import type { QuoteOption } from '../api/client'
import { formatDateTime, formatNumber, formatRmb } from '../utils/format'
import { ProvenanceBadge } from './ProvenanceBadge'

const tierLabels = { economy: '经济', balanced: '标准', quality: '高质量' }

export function QuoteOptions({
  options,
  onSelect,
  pendingQuoteId,
}: {
  options: QuoteOption[]
  onSelect: (quote: QuoteOption) => void
  pendingQuoteId?: string
}) {
  if (options.length === 0) return null
  const lowest = options.reduce((best, option) =>
    Number(option.total_price_rmb) < Number(best.total_price_rmb) ? option : best,
  )
  return (
    <section className="quote-section" aria-labelledby="quote-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">15 分钟内有效</p>
          <h2 id="quote-heading">选择执行方案</h2>
        </div>
        <ProvenanceBadge value="simulated" detail="pricing-sim-v1 与 synthetic-cn-east-v1" />
      </div>
      <div className="quote-grid">
        {options.map((option) => (
          <article className="quote-card" key={option.quote_id}>
            <div className="quote-title">
              <div>
                <span className={`tier-dot ${option.tier}`} />
                <strong>{tierLabels[option.tier]} · {option.model_name}</strong>
              </div>
              {option.quote_id === lowest.quote_id && <span className="badge success">最低价</span>}
            </div>
            <div className="quote-price">
              <span>{formatRmb(option.total_price_rmb)}</span>
              <small>仿真结算价</small>
            </div>
            <dl className="compact-metrics">
              <div><dt><Clock3 />执行</dt><dd>{option.execution_mode === 'flexible' ? '弹性' : '立即'}</dd></div>
              <div><dt><WalletCards />折扣</dt><dd>{formatNumber(option.discount_percent, 2)}%</dd></div>
              <div><dt><Gauge />机房能耗</dt><dd>{formatNumber(option.facility_energy_wh_est)} Wh</dd></div>
              <div><dt><Leaf />碳排</dt><dd>{formatNumber(option.carbon_g_est)} g</dd></div>
            </dl>
            <div className="quote-schedule">
              <span>{formatDateTime(option.scheduled_start)}</span>
              <span>绿电 {formatNumber(option.renewable_share_percent, 1)}%</span>
            </div>
            <button
              className="button primary full"
              onClick={() => onSelect(option)}
              disabled={pendingQuoteId !== undefined}
            >
              {pendingQuoteId === option.quote_id ? '正在创建' : '接受报价'}
              <ArrowRight aria-hidden="true" />
            </button>
          </article>
        ))}
      </div>
    </section>
  )
}
