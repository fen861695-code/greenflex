import { Brain, Leaf, ShieldCheck, Zap, Clock, AlertTriangle, CheckCircle2, Car, Smartphone, TreePine, TrendingDown } from 'lucide-react'
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

/** Carbon equivalents for intuitive understanding */
function carbonEquivalents(grams: number) {
  // Average gasoline car: ~150g CO2/km => 1g ≈ 6.67m
  const carMeters = grams * 6.67
  // Smartphone full charge: ~2.75g CO2 (China grid avg)
  const phoneCharges = grams / 2.75
  // Tree absorption: ~21kg/year => ~0.666mg/s => 1g ≈ 1500s ≈ 25min
  const treeMinutes = grams * 25
  return { carMeters, phoneCharges, treeMinutes }
}

function formatEquivalent(value: number, unit: string): string {
  if (value < 0.01) return `<0.01 ${unit}`
  if (value < 1) return `${value.toFixed(2)} ${unit}`
  if (value < 10) return `${value.toFixed(1)} ${unit}`
  return `${Math.round(value)} ${unit}`
}

/** Carbon level: 0-100 score based on grams (lower is greener) */
function carbonLevel(grams: number): { score: number; label: string; color: string } {
  // Reference scale: 0.001g = excellent, 0.1g = moderate, 1g+ = high
  if (grams < 0.01) return { score: 95, label: '极低', color: '#1a8f5c' }
  if (grams < 0.05) return { score: 80, label: '很低', color: '#2e9e63' }
  if (grams < 0.2) return { score: 60, label: '较低', color: '#6fa85a' }
  if (grams < 0.5) return { score: 40, label: '中等', color: '#d4940a' }
  if (grams < 1) return { score: 25, label: '较高', color: '#d4760a' }
  return { score: 10, label: '高', color: '#c0392b' }
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
  const carbon = parseFloat(recommendation.estimated_carbon_g)
  const price = parseFloat(recommendation.estimated_price_rmb)
  const energy = parseFloat(recommendation.estimated_energy_wh)
  const equiv = carbonEquivalents(carbon)
  const level = carbonLevel(carbon)

  // Find the most expensive/highest-carbon alternative for savings comparison
  const altPrices = recommendation.alternatives.map((a) => parseFloat(a.estimated_price_rmb))
  const altCarbons = recommendation.alternatives.map((a) => parseFloat(a.estimated_carbon_g))
  const maxPrice = Math.max(price, ...altPrices)
  const maxCarbon = Math.max(carbon, ...altCarbons)
  const priceSavings = maxPrice > 0 ? Math.round((1 - price / maxPrice) * 100) : 0
  const carbonSavings = maxCarbon > 0 ? Math.round((1 - carbon / maxCarbon) * 100) : 0

  return (
    <section className="recommendation-card rec-v2">
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
        {/* Model name + tier */}
        <div className="rec-model">
          <h4>{recommendation.recommended_model_name}</h4>
          <span className={`tier-badge tier-${recommendation.recommended_tier}`}>
            {recommendation.recommended_tier === 'economy'
              ? '经济档'
              : recommendation.recommended_tier === 'balanced'
                ? '标准档'
                : recommendation.recommended_tier === 'quality'
                  ? '高质量档'
                  : '旗舰档'}
          </span>
        </div>

        <p className="rec-summary">{recommendation.reason_summary}</p>

        {/* Core metrics row */}
        <div className="rec-metrics">
          <div className="metric">
            <Zap aria-hidden="true" />
            <div>
              <span className="metric-value">¥{price}</span>
              <span className="metric-label">预估费用</span>
            </div>
          </div>
          <div className="metric">
            <Clock aria-hidden="true" />
            <div>
              <span className="metric-value">{recommendation.estimated_execution_seconds}s</span>
              <span className="metric-label">预计耗时</span>
            </div>
          </div>
          <div className="metric">
            <Leaf aria-hidden="true" />
            <div>
              <span className="metric-value">{energy} Wh</span>
              <span className="metric-label">GPU 能耗</span>
            </div>
          </div>
        </div>

        {/* Carbon impact visual section */}
        <div className="carbon-impact">
          <div className="carbon-impact-header">
            <Leaf size={16} style={{ color: level.color }} />
            <span className="carbon-impact-title">碳排放影响</span>
            <span className="carbon-impact-badge" style={{ background: `${level.color}18`, color: level.color }}>
              {level.label}
            </span>
          </div>

          {/* Carbon gauge bar */}
          <div className="carbon-gauge">
            <div className="carbon-gauge-track">
              <div
                className="carbon-gauge-fill"
                style={{ width: `${level.score}%`, background: `linear-gradient(90deg, #1a8f5c, ${level.color})` }}
              />
              <div className="carbon-gauge-marker" style={{ left: `${level.score}%` }} />
            </div>
            <div className="carbon-gauge-labels">
              <span>零碳</span>
              <span>中等</span>
              <span>高碳</span>
            </div>
          </div>

          <div className="carbon-value-row">
            <span className="carbon-big-number" style={{ color: level.color }}>
              {carbon < 0.001 ? carbon.toExponential(1) : carbon.toFixed(4)}
            </span>
            <span className="carbon-unit">g CO₂</span>
          </div>

          {/* Intuitive equivalents */}
          <div className="carbon-equivalents">
            {equiv.carMeters >= 0.01 ? (
              <>
                <div className="equiv-item">
                  <Car size={15} />
                  <span>相当于燃油车行驶 <strong>{formatEquivalent(equiv.carMeters, '米')}</strong></span>
                </div>
                <div className="equiv-item">
                  <Smartphone size={15} />
                  <span>相当于手机充电 <strong>{formatEquivalent(equiv.phoneCharges, '次')}</strong></span>
                </div>
                <div className="equiv-item">
                  <TreePine size={15} />
                  <span>一棵树 <strong>{formatEquivalent(equiv.treeMinutes, '分钟')}</strong> 可吸收</span>
                </div>
              </>
            ) : (
              <>
                <div className="equiv-item">
                  <Car size={15} />
                  <span>千次调用相当于燃油车行驶 <strong>{formatEquivalent(equiv.carMeters * 1000, '米')}</strong></span>
                </div>
                <div className="equiv-item">
                  <Smartphone size={15} />
                  <span>千次调用相当于手机充电 <strong>{formatEquivalent(equiv.phoneCharges * 1000, '次')}</strong></span>
                </div>
                <div className="equiv-item">
                  <TreePine size={15} />
                  <span>千次调用一棵树 <strong>{formatEquivalent(equiv.treeMinutes * 1000, '分钟')}</strong> 可吸收</span>
                </div>
              </>
            )}
          </div>

          {/* Savings comparison */}
          {(priceSavings > 0 || carbonSavings > 0) && (
            <div className="carbon-savings">
              <TrendingDown size={14} />
              <span>
                相比其他可选模型{priceSavings > 0 && <>，费用节省 <strong>{priceSavings}%</strong></>}
                {carbonSavings > 0 && <>，碳排放减少 <strong>{carbonSavings}%</strong></>}
              </span>
            </div>
          )}
        </div>

        {/* Quality risk */}
        <div className={`quality-risk ${RISK_COLORS[recommendation.quality_risk]}`}>
          {recommendation.quality_risk === 'low' ? (
            <CheckCircle2 aria-hidden="true" />
          ) : (
            <AlertTriangle aria-hidden="true" />
          )}
          <span>质量风险：{RISK_LABELS[recommendation.quality_risk]}</span>
        </div>

        {/* Alternatives */}
        {recommendation.alternatives.length > 0 && (
          <details className="rec-alternatives">
            <summary>查看其他可选模型（{recommendation.alternatives.length}）</summary>
            <div className="alt-list">
              {recommendation.alternatives.map((alt) => (
                <div key={alt.model_id} className="alt-item">
                  <div className="alt-name">
                    <strong>{alt.model_name}</strong>
                    <span className={`tier-badge tier-${alt.tier}`}>
                      {alt.tier === 'economy' ? '经济' : alt.tier === 'balanced' ? '标准' : alt.tier === 'quality' ? '高质' : '旗舰'}
                    </span>
                  </div>
                  <div className="alt-metrics">
                    <span>¥{alt.estimated_price_rmb}</span>
                    <span>{alt.estimated_energy_wh} Wh</span>
                    <span>{alt.estimated_carbon_g} g</span>
                    <span>{alt.estimated_execution_seconds}s</span>
                  </div>
                  {alt.reason && <p className="alt-reason">{alt.reason}</p>}
                </div>
              ))}
            </div>
          </details>
        )}

        <p className="rec-note">影子模式：推荐结果仅作参考，不会自动下单。请确认后继续。</p>

        <div className="rec-actions">
          <button type="button" className="button ghost" onClick={onReject}>
            手动选择
          </button>
          <button type="button" className="button primary" onClick={onAccept} disabled={loading}>
            {loading ? '正在计算报价...' : '使用推荐模型'}
          </button>
        </div>
      </div>
    </section>
  )
}
