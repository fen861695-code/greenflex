import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Download, FileCheck2, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react'
import { api, apiMessage, type ComplianceReport } from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { formatDateTime } from '../utils/format'

const statusLabels: Record<string, string> = {
  compliant: '合规',
  partial: '部分合规',
  non_compliant: '不合规',
  not_applicable: '不适用',
}

const statusIcons: Record<string, typeof CheckCircle2> = {
  compliant: CheckCircle2,
  partial: AlertTriangle,
  non_compliant: XCircle,
  not_applicable: ShieldCheck,
}

export function CompliancePage() {
  const report = useQuery<ComplianceReport>({
    queryKey: ['compliance-report'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/compliance/ai-act')
      if (error) throw new Error(apiMessage(error))
      return data as ComplianceReport
    },
  })

  const handleDownloadMarkdown = () => {
    window.open('/api/v1/compliance/ai-act/markdown', '_blank')
  }

  if (report.isLoading) return <main className="page"><LoadingState label="生成合规报告" /></main>
  if (report.isError || !report.data) return <main className="page"><ErrorState message={apiMessage(report.error)} /></main>

  const r = report.data
  const summary = r.summary
  const score = summary.compliance_score_percent
  const scoreColor = score >= 80 ? '#237451' : score >= 50 ? '#8a630f' : '#a13d3d'

  return (
    <main className="page compliance-page">
      <PageHeader
        eyebrow="EU AI Act 合规"
        title="AI 法案合规报告"
        actions={
          <>
            <ProvenanceBadge value="simulated" detail="合规评估为自动生成，非官方认证" />
            <button className="button secondary" onClick={handleDownloadMarkdown}>
              <Download aria-hidden="true" />
              下载 Markdown
            </button>
          </>
        }
      />

      {/* 报告元信息 */}
      <div className="compliance-meta">
        <div>
          <span>报告 ID</span>
          <strong className="hash-value">{r.report_id}</strong>
        </div>
        <div>
          <span>生成时间</span>
          <strong>{formatDateTime(r.generated_at)}</strong>
        </div>
        <div>
          <span>法规</span>
          <strong>{r.regulation}</strong>
        </div>
        <div>
          <span>报告版本</span>
          <strong>{r.report_version}</strong>
        </div>
      </div>

      {/* 合规评分概览 */}
      <section className="compliance-overview">
        <div className="compliance-score-ring">
          <svg viewBox="0 0 120 120" width="120" height="120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="#e8edeb" strokeWidth="10" />
            <circle
              cx="60" cy="60" r="52" fill="none" stroke={scoreColor} strokeWidth="10"
              strokeDasharray={`${String((score / 100) * 326.7)} 326.7`}
              strokeLinecap="round" transform="rotate(-90 60 60)"
            />
            <text x="60" y="55" textAnchor="middle" fontSize="28" fontWeight="700" fill={scoreColor}>{score.toFixed(1)}%</text>
            <text x="60" y="75" textAnchor="middle" fontSize="11" fill="#63706c">合规评分</text>
          </svg>
        </div>

        <div className="compliance-summary-stats">
          <div className="compliance-stat">
            <CheckCircle2 aria-hidden="true" className="icon-compliant" />
            <div>
              <span>合规</span>
              <strong>{summary.compliant}</strong>
            </div>
          </div>
          <div className="compliance-stat">
            <AlertTriangle aria-hidden="true" className="icon-partial" />
            <div>
              <span>部分合规</span>
              <strong>{summary.partial}</strong>
            </div>
          </div>
          <div className="compliance-stat">
            <XCircle aria-hidden="true" className="icon-non-compliant" />
            <div>
              <span>不合规</span>
              <strong>{summary.non_compliant}</strong>
            </div>
          </div>
          <div className="compliance-stat">
            <ShieldCheck aria-hidden="true" className="icon-na" />
            <div>
              <span>不适用</span>
              <strong>{summary.not_applicable}</strong>
            </div>
          </div>
        </div>

        <div className="compliance-status-card">
          <div className="compliance-status-header">
            <FileCheck2 aria-hidden="true" />
            <span>总体状态</span>
          </div>
          <strong className={`status-${summary.overall_status}`}>{summary.overall_status.toUpperCase()}</strong>
          <small>风险等级：{summary.risk_level}</small>
          <small>适用检查项：{summary.applicable_checks} / {summary.total_checks}</small>
        </div>
      </section>

      {/* 高严重度问题 */}
      {summary.high_severity_issues.length > 0 && (
        <section className="compliance-section">
          <div className="section-heading">
            <h2><ShieldAlert aria-hidden="true" /> 高严重度问题</h2>
            <span className="badge danger">{summary.high_severity_issues_count} 项</span>
          </div>
          <div className="high-severity-list">
            {summary.high_severity_issues.map((issue, i) => (
              <div key={i} className="high-severity-item">
                <span className="badge danger">{issue.article}</span>
                <div>
                  <strong>{issue.requirement}</strong>
                  <small>状态：{statusLabels[issue.status] ?? issue.status}</small>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 平台信息 */}
      <section className="compliance-section">
        <div className="section-heading"><h2>平台信息</h2></div>
        <div className="platform-info-grid">
          <div><span>版本</span><strong>{r.platform_info.version}</strong></div>
          <div><span>部署类型</span><strong>{r.platform_info.deployment_type}</strong></div>
          <div><span>API 边界</span><strong>{r.platform_info.api_bound}</strong></div>
          <div><span>用户认证</span><strong>{r.platform_info.user_authentication ? '已启用' : '未启用'}</strong></div>
          <div><span>审计日志</span><strong>{r.platform_info.audit_logging ? '已启用' : '未启用'}</strong></div>
          <div><span>内容清除</span><strong>{r.platform_info.content_purge ? '已支持' : '不支持'}</strong></div>
          <div><span>C2PA 支持</span><strong>{r.platform_info.c2pa_support ? '已支持' : '不支持'}</strong></div>
          <div><span>能耗报告</span><strong>{r.platform_info.energy_reporting ? '已支持' : '不支持'}</strong></div>
          <div><span>碳排报告</span><strong>{r.platform_info.carbon_reporting ? '已支持' : '不支持'}</strong></div>
        </div>
      </section>

      {/* 详细检查项 */}
      <section className="compliance-section">
        <div className="section-heading"><h2>详细检查项</h2></div>
        <div className="table-wrap">
          <table className="data-table compliance-table">
            <thead>
              <tr>
                <th style={{ width: '100px' }}>条款</th>
                <th>要求</th>
                <th style={{ width: '100px' }}>状态</th>
                <th>证据</th>
                <th>建议</th>
              </tr>
            </thead>
            <tbody>
              {r.checks.map((check, i) => {
                const StatusIcon = statusIcons[check.status] ?? ShieldCheck
                return (
                  <tr key={i}>
                    <td><code>{check.article}</code></td>
                    <td>{check.requirement}</td>
                    <td>
                      <span className={`badge ${check.status}`}>
                        <StatusIcon aria-hidden="true" />
                        {statusLabels[check.status] ?? check.status}
                      </span>
                    </td>
                    <td><small>{check.evidence}</small></td>
                    <td><small>{check.recommendation ?? '—'}</small></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="compliance-disclaimer">
        <ShieldAlert aria-hidden="true" />
        <span>本报告由 GreenFlex 自动生成，用于演示 EU AI Act 合规评估能力，不构成法律意见或官方认证。实际合规性请咨询专业法律顾问。</span>
      </div>
    </main>
  )
}
