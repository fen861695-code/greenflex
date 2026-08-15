import { useQuery } from '@tanstack/react-query'
import { Leaf, Clock, TrendingDown, Zap, Car, MapPin } from 'lucide-react'

import { api, apiMessage } from '../api/client'
import { CarbonCalendarHeatmap } from '../components/CarbonCalendarHeatmap'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'

type GridRegion = {
  code: string
  name_zh: string
  carbon_g_per_kwh: number
  renewable_share_bps: number
}

type GridRegionData = {
  current: string
  regions: GridRegion[]
}

export function CarbonSignalPage() {
  const regionsQuery = useQuery<GridRegionData>({
    queryKey: ['grid-regions'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/signals/regions')
      if (error) throw new Error(apiMessage(error))
      return data as GridRegionData
    },
  })

  const regions = regionsQuery.data?.regions ?? []
  const sorted = [...regions].sort((a, b) => a.carbon_g_per_kwh - b.carbon_g_per_kwh)
  const greenest = sorted[0]
  const dirtiest = sorted[sorted.length - 1]
  const avgCarbon = regions.length > 0
    ? Math.round(regions.reduce((s, r) => s + r.carbon_g_per_kwh, 0) / regions.length)
    : 0
  const savingPct = greenest && dirtiest
    ? Math.round((1 - greenest.carbon_g_per_kwh / dirtiest.carbon_g_per_kwh) * 100)
    : 0
  const carMetersSaved = greenest && dirtiest
    ? Math.round((dirtiest.carbon_g_per_kwh - greenest.carbon_g_per_kwh) * 6.67)
    : 0

  return (
    <main className="page carbon-signal-page">
      <PageHeader
        eyebrow="绿色信号"
        title="电网碳强度监控"
        description="实时追踪全国七大电网碳排放强度，选择绿色时段和区域调度推理任务，在不牺牲质量的前提下减少碳排放。"
        actions={<ProvenanceBadge value="estimated" detail="基于区域电网2023官方因子的分时模型" />}
      />

      {/* Summary cards */}
      {regions.length > 0 && (
        <div className="carbon-summary-cards">
          <div className="carbon-summary-card summary-green">
            <div className="summary-icon"><Leaf size={18} /></div>
            <div className="summary-body">
              <span className="summary-label">最清洁电网</span>
              <strong>{greenest?.name_zh}</strong>
              <span className="summary-value">{greenest?.carbon_g_per_kwh} g CO₂/kWh</span>
            </div>
          </div>
          <div className="carbon-summary-card summary-red">
            <div className="summary-icon"><Zap size={18} /></div>
            <div className="summary-body">
              <span className="summary-label">最高碳强度</span>
              <strong>{dirtiest?.name_zh}</strong>
              <span className="summary-value">{dirtiest?.carbon_g_per_kwh} g CO₂/kWh</span>
            </div>
          </div>
          <div className="carbon-summary-card summary-blue">
            <div className="summary-icon"><MapPin size={18} /></div>
            <div className="summary-body">
              <span className="summary-label">全国平均</span>
              <strong>{avgCarbon} g/kWh</strong>
              <span className="summary-value">7 大电网均值</span>
            </div>
          </div>
          <div className="carbon-summary-card summary-emerald">
            <div className="summary-icon"><TrendingDown size={18} /></div>
            <div className="summary-body">
              <span className="summary-label">区域调度潜力</span>
              <strong>省 {savingPct}%</strong>
              <span className="summary-value">
                <Car size={12} /> 每度电少开 {carMetersSaved} 米
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Explanation banner */}
      <div className="carbon-explain">
        <Clock size={16} />
        <span>
          碳排放因电网构成和用电时段不同而差异显著。风电、光伏等可再生能源占比高的电网和时段，
          AI 推理的碳足迹更低。开启"弹性执行"后，GreenFlex 会自动将任务调度到绿色时段。
        </span>
      </div>

      {/* Full carbon dashboard (map + ranking + heatmap) */}
      <CarbonCalendarHeatmap showHeader={false} />
    </main>
  )
}
