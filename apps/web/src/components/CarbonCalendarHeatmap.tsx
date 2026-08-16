import { useQuery } from '@tanstack/react-query'
import { Fragment, useState } from 'react'
import { Leaf, TrendingDown, Clock, Zap, Car, TreePine } from 'lucide-react'

import { api, apiMessage, type CarbonCalendarData } from '../api/client'
import { ProvenanceBadge } from './ProvenanceBadge'

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

function carbonColor(value: number, min: number, max: number): string {
  if (max === min) return '#22c55e'
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)))
  const stops = [
    { t: 0, r: 34, g: 197, b: 94 },
    { t: 0.4, r: 132, g: 204, b: 22 },
    { t: 0.65, r: 234, g: 179, b: 8 },
    { t: 0.82, r: 249, g: 115, b: 22 },
    { t: 1, r: 239, g: 68, b: 68 },
  ]
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i].t) {
      const prev = stops[i - 1]
      const curr = stops[i]
      const span = curr.t - prev.t
      const f = span === 0 ? 0 : (t - prev.t) / span
      const r = Math.round(prev.r + (curr.r - prev.r) * f)
      const g = Math.round(prev.g + (curr.g - prev.g) * f)
      const b = Math.round(prev.b + (curr.b - prev.b) * f)
      return `rgb(${String(r)}, ${String(g)}, ${String(b)})`
    }
  }
  return 'rgb(239, 68, 68)'
}

// Region positions on the SVG map (viewBox 0 0 500 440)
const REGION_POSITIONS: Record<string, { x: number; y: number; labelX: number; labelY: number; anchor: string }> = {
  'CN-Northwest':  { x: 130, y: 175, labelX: 100, labelY: 150, anchor: 'end' },
  'CN-North':      { x: 290, y: 155, labelX: 310, labelY: 130, anchor: 'start' },
  'CN-Northeast':  { x: 400, y: 100, labelX: 410, labelY: 75,  anchor: 'start' },
  'CN-Southwest':  { x: 200, y: 290, labelX: 170, labelY: 315, anchor: 'end' },
  'CN-Central':    { x: 300, y: 260, labelX: 320, labelY: 285, anchor: 'start' },
  'CN-East':       { x: 380, y: 270, labelX: 400, labelY: 250, anchor: 'start' },
  'CN-South':      { x: 310, y: 350, labelX: 330, labelY: 380, anchor: 'start' },
}

const CHINA_OUTLINE = 'M 80,180 L 100,120 L 160,80 L 220,60 L 280,55 L 340,65 L 400,55 L 440,80 L 460,110 L 450,150 L 430,170 L 420,200 L 430,230 L 420,270 L 400,300 L 380,340 L 360,370 L 330,390 L 300,400 L 270,395 L 240,380 L 210,360 L 180,340 L 150,320 L 120,290 L 90,260 L 70,230 Z'

const REGION_RADIUS: Record<string, number> = {
  'CN-Northwest':  65,
  'CN-North':      45,
  'CN-Northeast':  48,
  'CN-Southwest':  50,
  'CN-Central':    42,
  'CN-East':       40,
  'CN-South':      48,
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

export function CarbonCalendarHeatmap({ showHeader = true }: { showHeader?: boolean }) {
  const [region, setRegion] = useState<string | null>(null)
  const [hoveredRegion, setHoveredRegion] = useState<string | null>(null)

  const regionsQuery = useQuery<GridRegionData>({
    queryKey: ['grid-regions'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/signals/regions')
      if (error) throw new Error(apiMessage(error))
      return data as GridRegionData
    },
  })

  const calendarQuery = useQuery<CarbonCalendarData>({
    queryKey: ['carbon-calendar', region],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/signals/calendar', {
        params: { query: { days: 7, ...(region ? { region } : {}) } },
      })
      if (error) throw new Error(apiMessage(error))
      return data as CarbonCalendarData
    },
  })

  if (calendarQuery.isLoading) return <div className="carbon-calendar loading">加载碳强度日历...</div>
  if (calendarQuery.error || !calendarQuery.data) return <div className="carbon-calendar error">碳强度日历不可用</div>

  const data = calendarQuery.data
  const allHours = data.days.flatMap((d) => d.hours)
  const min = Math.min(...allHours.map((h) => h.carbon_g_per_kwh))
  const max = Math.max(...allHours.map((h) => h.carbon_g_per_kwh))
  const regions = regionsQuery.data?.regions ?? []

  const carbonMin = regions.length > 0 ? Math.min(...regions.map((r) => r.carbon_g_per_kwh)) : 0
  const carbonMax = regions.length > 0 ? Math.max(...regions.map((r) => r.carbon_g_per_kwh)) : 1000

  const sortedRegions = [...regions].sort((a, b) => a.carbon_g_per_kwh - b.carbon_g_per_kwh)
  const greenest = sortedRegions[0]
  const dirtiest = sortedRegions[sortedRegions.length - 1]

  const allHoursWithDay = data.days.flatMap((d) =>
    d.hours.map((h) => ({ ...h, date: d.date })),
  )
  const bestHour = allHoursWithDay.reduce((a, b) => (a.carbon_g_per_kwh < b.carbon_g_per_kwh ? a : b))
  const worstHour = allHoursWithDay.reduce((a, b) => (a.carbon_g_per_kwh > b.carbon_g_per_kwh ? a : b))

  const selectedRegion = region ?? data.region
  const selectedRegionData = regions.find((r) => r.code === selectedRegion)

  // Carbon saving potential: scheduling at best hour vs worst hour
  const savingPct = worstHour.carbon_g_per_kwh > 0
    ? Math.round((1 - bestHour.carbon_g_per_kwh / worstHour.carbon_g_per_kwh) * 100)
    : 0

  // Equivalent: per 1 kWh at best vs worst, how much CO2 saved
  const co2SavedPerKwh = worstHour.carbon_g_per_kwh - bestHour.carbon_g_per_kwh
  // 1 kWh at best hour, car meters equivalent
  const carMetersSaved = co2SavedPerKwh * 6.67

  return (
    <div className="carbon-calendar-v2">
      {showHeader && (
        <div className="calendar-header">
          <div>
            <h3>电网碳强度监控</h3>
            <p>实时追踪全国七大电网碳排放强度，智能调度至绿色时段</p>
          </div>
          <div className="calendar-header-right">
            <ProvenanceBadge value="estimated" detail="基于区域电网2023官方因子的分时模型" />
          </div>
        </div>
      )}

      {/* Green scheduling insight banner */}
      <div className="carbon-insight-banner">
        <div className="insight-icon">
          <Leaf size={20} />
        </div>
        <div className="insight-content">
          <div className="insight-title">
            绿色调度建议：{bestHour.date.slice(5)} {String(bestHour.hour).padStart(2, '0')}:00 最清洁
          </div>
          <div className="insight-desc">
            此时段碳强度仅 <strong>{bestHour.carbon_g_per_kwh} g/kWh</strong>（可再生能源 {(bestHour.renewable_share_bps / 100).toFixed(0)}%），
            比最高碳时段减少 <strong>{savingPct}%</strong> 碳排放。
            每消耗 1 度电，相当于少开燃油车 <strong>{Math.round(carMetersSaved)} 米</strong>。
          </div>
        </div>
        <div className="insight-saving">
          <TrendingDown size={16} />
          <span>省{savingPct}%</span>
        </div>
      </div>

      {/* China Map + Stats */}
      <div className="carbon-dashboard">
        <div className="china-map-panel">
          <div className="map-title">
            <span>中国七大电网区域</span>
            <span className="map-subtitle">点击区域查看分时碳强度</span>
          </div>
          <svg viewBox="0 0 500 440" className="china-svg" role="img" aria-label="中国电网碳强度地图">
            <defs>
              <radialGradient id="mapGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="rgba(34,197,94,0.08)" />
                <stop offset="100%" stopColor="rgba(34,197,94,0)" />
              </radialGradient>
              <filter id="regionGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="regionGlowStrong" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="8" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <ellipse cx="260" cy="230" rx="230" ry="190" fill="url(#mapGlow)" />

            <path
              d={CHINA_OUTLINE}
              fill="rgba(148,163,184,0.06)"
              stroke="rgba(148,163,184,0.25)"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />

            {regions.length >= 2 && (
              <g className="region-connections" opacity="0.15">
                {regions.map((r, i) =>
                  regions.slice(i + 1).map((r2) => {
                    const p1 = REGION_POSITIONS[r.code]
                    const p2 = REGION_POSITIONS[r2.code]
                    if (!p1 || !p2) return null
                    return (
                      <line
                        key={`${r.code}-${r2.code}`}
                        x1={p1.x}
                        y1={p1.y}
                        x2={p2.x}
                        y2={p2.y}
                        stroke="#94a3b8"
                        strokeWidth="0.5"
                        strokeDasharray="2,3"
                      />
                    )
                  }),
                )}
              </g>
            )}

            {regions.map((r) => {
              const pos = REGION_POSITIONS[r.code]
              if (!pos) return null
              const color = carbonColor(r.carbon_g_per_kwh, carbonMin, carbonMax)
              const isSelected = r.code === selectedRegion
              const isHovered = r.code === hoveredRegion
              const radius = REGION_RADIUS[r.code] ?? 40
              return (
                <g
                  key={r.code}
                  className={`region-group ${isSelected ? 'selected' : ''} ${isHovered ? 'hovered' : ''}`}
                  onClick={() => setRegion(isSelected ? null : r.code)}
                  onMouseEnter={() => setHoveredRegion(r.code)}
                  onMouseLeave={() => setHoveredRegion(null)}
                  style={{ cursor: 'pointer' }}
                >
                  {isSelected && (
                    <circle cx={pos.x} cy={pos.y} r={radius + 8} fill="none" stroke={color} strokeWidth="1.5" opacity="0.5">
                      <animate attributeName="r" values={`${String(radius)};${String(radius + 15)};${String(radius)}`} dur="2s" repeatCount="indefinite" />
                      <animate attributeName="opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <circle
                    cx={pos.x}
                    cy={pos.y}
                    r={radius}
                    fill={color}
                    opacity={isSelected ? 0.35 : isHovered ? 0.28 : 0.18}
                    filter={isSelected ? 'url(#regionGlowStrong)' : 'url(#regionGlow)'}
                  />
                  <circle
                    cx={pos.x}
                    cy={pos.y}
                    r={isSelected ? radius * 0.55 : isHovered ? radius * 0.5 : radius * 0.42}
                    fill={color}
                    opacity={0.85}
                    style={{ transition: 'r 0.3s ease' }}
                  />
                  <circle cx={pos.x} cy={pos.y} r={3} fill="#fff" opacity={0.9} />
                  <text
                    x={pos.labelX}
                    y={pos.labelY}
                    textAnchor={pos.anchor}
                    className="region-label"
                    fill={isSelected ? color : '#cbd5e1'}
                    fontSize={isSelected ? 13 : 11}
                    fontWeight={isSelected ? 700 : 500}
                  >
                    {r.name_zh}
                  </text>
                  <text
                    x={pos.labelX}
                    y={pos.labelY + 14}
                    textAnchor={pos.anchor}
                    className="region-value"
                    fill={isSelected ? color : '#94a3b8'}
                    fontSize={isSelected ? 12 : 10}
                    fontWeight={600}
                  >
                    {r.carbon_g_per_kwh} g/kWh
                  </text>
                </g>
              )
            })}

            <g transform="translate(420, 380)">
              <rect x="0" y="0" width="55" height="45" rx="4" fill="none" stroke="rgba(148,163,184,0.2)" strokeWidth="0.8" />
              <path d="M 5,35 Q 15,20 25,28 Q 35,15 50,25" fill="none" stroke="rgba(148,163,184,0.3)" strokeWidth="0.8" />
              <circle cx="30" cy="30" r="2" fill="rgba(34,197,94,0.5)" />
            </g>
          </svg>

          <div className="map-legend">
            <span>低碳</span>
            <div className="map-legend-bar" />
            <span>高碳</span>
            <span className="map-legend-unit">g CO₂/kWh</span>
          </div>
        </div>

        {/* Stats panel */}
        <div className="carbon-stats-panel">
          {selectedRegionData && (
            <div className="stats-selected">
              <div className="stats-selected-header">
                <span
                  className="stats-dot"
                  style={{ backgroundColor: carbonColor(selectedRegionData.carbon_g_per_kwh, carbonMin, carbonMax) }}
                />
                <strong>{selectedRegionData.name_zh}</strong>
                {region && (
                  <button className="stats-clear" onClick={() => setRegion(null)}>
                    查看全国
                  </button>
                )}
              </div>
              <div className="stats-big-number" style={{ color: carbonColor(selectedRegionData.carbon_g_per_kwh, carbonMin, carbonMax) }}>
                {selectedRegionData.carbon_g_per_kwh}
                <small>g CO₂/kWh</small>
              </div>
              <div className="stats-renewable">
                <div className="renewable-bar-track">
                  <div
                    className="renewable-bar-fill"
                    style={{ width: `${(selectedRegionData.renewable_share_bps / 100).toFixed(0)}%` }}
                  />
                </div>
                <span>可再生能源占比 {(selectedRegionData.renewable_share_bps / 100).toFixed(0)}%</span>
              </div>
              {/* Intuitive equivalent for selected region */}
              <div className="stats-equivalent">
                <Car size={13} />
                <span>每度电相当于燃油车行驶 <strong>{Math.round(selectedRegionData.carbon_g_per_kwh * 6.67)} 米</strong></span>
              </div>
            </div>
          )}

          <div className="stats-grid">
            {greenest && (
              <div className="stat-card stat-green">
                <span className="stat-label"><Leaf size={12} /> 最清洁电网</span>
                <strong>{greenest.name_zh}</strong>
                <span className="stat-value">{greenest.carbon_g_per_kwh} g/kWh</span>
              </div>
            )}
            {dirtiest && (
              <div className="stat-card stat-red">
                <span className="stat-label"><Zap size={12} /> 最高碳强度</span>
                <strong>{dirtiest.name_zh}</strong>
                <span className="stat-value">{dirtiest.carbon_g_per_kwh} g/kWh</span>
              </div>
            )}
          </div>

          <div className="stats-grid">
            <div className="stat-card stat-blue">
              <span className="stat-label"><Clock size={12} /> 最佳推理时段</span>
              <strong>{bestHour.date.slice(5)} {String(bestHour.hour).padStart(2, '0')}:00</strong>
              <span className="stat-value">{bestHour.carbon_g_per_kwh} g/kWh · 可再生{(bestHour.renewable_share_bps / 100).toFixed(0)}%</span>
            </div>
            <div className="stat-card stat-orange">
              <span className="stat-label"><Clock size={12} /> 最高碳时段</span>
              <strong>{worstHour.date.slice(5)} {String(worstHour.hour).padStart(2, '0')}:00</strong>
              <span className="stat-value">{worstHour.carbon_g_per_kwh} g/kWh · 可再生{(worstHour.renewable_share_bps / 100).toFixed(0)}%</span>
            </div>
          </div>

          {/* Region ranking with bars */}
          <div className="region-ranking">
            <div className="ranking-title">电网碳强度排行（从绿到高）</div>
            {sortedRegions.map((r, i) => {
              const pct = carbonMax > carbonMin ? ((r.carbon_g_per_kwh - carbonMin) / (carbonMax - carbonMin)) * 100 : 0
              const barColor = carbonColor(r.carbon_g_per_kwh, carbonMin, carbonMax)
              return (
                <button
                  key={r.code}
                  className={`ranking-row ${r.code === selectedRegion ? 'active' : ''}`}
                  onClick={() => setRegion(r.code === selectedRegion ? null : r.code)}
                >
                  <span className="ranking-rank">{i + 1}</span>
                  <span className="ranking-name">{r.name_zh}</span>
                  <div className="ranking-bar-track">
                    <div
                      className="ranking-bar-fill"
                      style={{ width: `${Math.max(pct, 8)}%`, background: barColor }}
                    />
                  </div>
                  <span className="ranking-value">{r.carbon_g_per_kwh}</span>
                  <span className="ranking-renewable">{(r.renewable_share_bps / 100).toFixed(0)}%</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Hourly heatmap */}
      <div className="heatmap-section">
        <div className="heatmap-title">
          <span>未来7天分时碳强度 · {regions.find((r) => r.code === selectedRegion)?.name_zh ?? '全国'}</span>
          <span className="heatmap-hint">颜色越绿碳排放越低，适合调度推理任务</span>
        </div>
        <div className="calendar-grid-wrapper">
          <div className="calendar-grid">
            <div className="calendar-corner" />
            {Array.from({ length: 24 }, (_, h) => (
              <div key={h} className="calendar-hour-label">{h}</div>
            ))}
            {data.days.map((day) => {
              const date = new Date(day.date)
              const weekday = WEEKDAYS[(date.getDay() + 6) % 7]
              return (
                <Fragment key={day.date}>
                  <div className="calendar-day-label">
                    <span className="day-weekday">周{weekday}</span>
                    <span className="day-date">{day.date.slice(5)}</span>
                  </div>
                  {day.hours.map((hour) => (
                    <div
                      key={hour.hour}
                      className="calendar-cell"
                      style={{ backgroundColor: carbonColor(hour.carbon_g_per_kwh, min, max) }}
                      title={`${day.date} ${String(hour.hour).padStart(2, '0')}:00 - ${String(hour.carbon_g_per_kwh)} g/kWh, 可再生 ${(hour.renewable_share_bps / 100).toFixed(0)}%`}
                    />
                  ))}
                </Fragment>
              )
            })}
          </div>
        </div>
        <div className="calendar-legend">
          <span>{String(min)} g/kWh</span>
          <div className="legend-gradient" />
          <span>{String(max)} g/kWh</span>
        </div>
      </div>
    </div>
  )
}
