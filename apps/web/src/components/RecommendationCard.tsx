import { Brain, Leaf, ShieldCheck, Zap, Clock, AlertTriangle, CheckCircle2, Database } from 'lucide-react'
import type { RecommendationResponse, QualityRiskLevel } from '../api/client'

const RISK_LABELS: Record<QualityRiskLevel, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  very_high: '极高风险',
}

const RISK_COLORS: Record<QualityRiskLevel, string> = {
  low: 'risk-low',
  medium: 'risk-medium',
  high: 'risk-high',
  very_high: 'risk-very-high',
}

const MODE_LABELS: Record<string, string> = {
  smart: '智能推荐',
  economy: '经济优先',
  quality: '质量优先',
  manual: '手动选择',
}

// Energy data provenance tier labels and colors (L1-L3 + insufficient only)
const ENERGY_TIER_LABELS: Record<string, string> = {
  l1_local_measured: '本地实测',
  l2_benchmark_match: '公开基准',
  l3_cross_gpu_normalized: '跨GPU归一化',
  insufficient_data: '数据不足',
}

const ENERGY_TIER_COLORS: Record<string, string> = {
  l1_local_measured: 'provenance-l1',
  l2_benchmark_match: 'provenance-l2',
  l3_cross_gpu_normalized: 'provenance-l3',
  insufficient_data: 'provenance-insufficient',
}

function confidenceLabel(confidenceBps: number): string {
  if (confidenceBps >= 8000) return '高'
  if (confidenceBps >= 5000) return '中'
  return '低'
}

interface RecommendationCardProps {
  recommendation: RecommendationResponse
  onAccept: () => void
  onReject: () => void
  loading?: boolean
}

export function RecommendationCard({
  recommendation,
  onAccept,
  onReject,
  loading,
}: RecommendationCardProps) {
  return (
    <section className="recommendation-card">
      <header className="rec-header">
        <div className="rec-title">
          <Brain aria-hidden="true" />
          <div>
            <h3>GreenRouter 智能推荐</h3>
            <span className="rec-mode">{MODE_LABELS[recommendation.recommended_mode]}</span>
          </div>
        </div>
        <div className={`confidence-badge confidence-${recommendation.confidence_label}`}>
          置信度：{recommendation.confidence_label}
        </div>
      </header>

      <div className="rec-body">
        <div className="rec-model">
          <h4>{recommendation.recommended_model_name}</h4>
          <span className={`tier-badge tier-${recommendation.recommended_tier}`}>
            {recommendation.recommended_tier === 'economy'
              ? '经济档'
              : recommendation.recommended_tier === 'balanced'
                ? '标准档'
                : '高质量档'}
          </span>
        </div>

        <p className="rec-summary">{recommendation.reason_summary}</p>

        <div className="rec-metrics">
          <div className="metric">
            <Zap aria-hidden="true" />
            <div>
              <span className="metric-value">¥{recommendation.estimated_price_rmb}</span>
              <span className="metric-label">预估费用</span>
            </div>
          </div>
          <div className="metric">
            <Leaf aria-hidden="true" />
            <div>
              <span className="metric-value">{recommendation.estimated_energy_wh} Wh</span>
              <span className="metric-label">GPU 能耗</span>
            </div>
          </div>
          <div className="metric">
            <ShieldCheck aria-hidden="true" />
            <div>
              <span className="metric-value">{recommendation.estimated_carbon_g} g</span>
              <span className="metric-label">碳排放</span>
            </div>
          </div>
          <div className="metric">
            <Clock aria-hidden="true" />
            <div>
              <span className="metric-value">{recommendation.estimated_execution_seconds}s</span>
              <span className="metric-label">预计耗时</span>
            </div>
          </div>
        </div>

        <div className={`quality-risk ${RISK_COLORS[recommendation.quality_risk]}`}>
          {recommendation.quality_risk === 'low' ? (
            <CheckCircle2 aria-hidden="true" />
          ) : (
            <AlertTriangle aria-hidden="true" />
          )}
          <span>质量风险：{RISK_LABELS[recommendation.quality_risk]}</span>
        </div>

        {/* Energy data provenance badge (v2) */}
        <div className={`energy-provenance ${ENERGY_TIER_COLORS[recommendation.energy_provenance_tier] || 'provenance-insufficient'}`}>
          <Database aria-hidden="true" />
          <div>
            <span className="provenance-label">
              能耗数据：{ENERGY_TIER_LABELS[recommendation.energy_provenance_tier] || '数据不足'}
            </span>
            <span className="provenance-confidence">
              可信度：{confidenceLabel(recommendation.energy_confidence_bps)}（{recommendation.energy_confidence_bps / 100}%）
            </span>
            {recommendation.energy_source_description && (
              <span className="provenance-source">{recommendation.energy_source_description}</span>
            )}
          </div>
        </div>

        {/* Carbon intensity source badge (v2) */}
        {recommendation.carbon_intensity_source && (
          <div className="carbon-source">
            <Leaf aria-hidden="true" />
            <span>
              碳强度来源：{recommendation.carbon_intensity_source}
              {recommendation.carbon_intensity_provenance === 'simulated' && (
                <span className="carbon-simulated">（模拟数据）</span>
              )}
            </span>
          </div>
        )}

        {recommendation.alternatives.length > 0 && (
          <details className="rec-alternatives">
            <summary>查看其他可选模型（{recommendation.alternatives.length}）</summary>
            <div className="alt-list">
              {recommendation.alternatives.map((alt) => (
                <div key={alt.model_id} className="alt-item">
                  <div className="alt-name">
                    <strong>{alt.model_name}</strong>
                    <span className={`tier-badge tier-${alt.tier}`}>
                      {alt.tier === 'economy' ? '经济' : alt.tier === 'balanced' ? '标准' : '高质量'}
                    </span>
                  </div>
                  <div className="alt-stats">
                    <span>¥{alt.estimated_price_rmb} ({alt.price_diff_pct}%)</span>
                    <span>{alt.estimated_energy_wh} Wh ({alt.energy_diff_pct}%)</span>
                    <span className={RISK_COLORS[alt.quality_risk]}>
                      {RISK_LABELS[alt.quality_risk]}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </details>
        )}

        {recommendation.shadow_mode && (
          <div className="shadow-notice">
            <AlertTriangle aria-hidden="true" />
            <span>影子模式：推荐结果仅作参考，不会自动下单。请确认后继续。</span>
          </div>
        )}
      </div>

      <footer className="rec-actions">
        <button type="button" className="button ghost" onClick={onReject} disabled={loading}>
          手动选择
        </button>
        <button type="button" className="button primary" onClick={onAccept} disabled={loading}>
          使用推荐模型
        </button>
      </footer>
    </section>
  )
}
