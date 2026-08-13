import { useQuery } from '@tanstack/react-query'
import { BadgeCheck, FileCheck2, ShieldCheck } from 'lucide-react'
import { api, apiMessage, type C2PAManifest } from '../api/client'
import { formatDateTime, formatNumber } from '../utils/format'

interface C2PABadgeProps {
  passportId: string
  compact?: boolean
}

export function C2PABadge({ passportId, compact = false }: C2PABadgeProps) {
  const c2pa = useQuery<C2PAManifest>({
    queryKey: ['c2pa', passportId],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/passports/{passport_id}/c2pa', {
        params: { path: { passport_id: passportId } },
      })
      if (error) throw new Error(apiMessage(error))
      return data as C2PAManifest
    },
    enabled: !!passportId,
  })

  if (c2pa.isLoading) {
    return (
      <div className="c2pa-badge c2pa-loading">
        <ShieldCheck aria-hidden="true" className="spin" />
        <span>验证 C2PA 凭证...</span>
      </div>
    )
  }

  if (c2pa.isError || !c2pa.data) {
    return (
      <div className="c2pa-badge c2pa-unavailable">
        <FileCheck2 aria-hidden="true" />
        <span>C2PA 凭证不可用</span>
      </div>
    )
  }

  const manifest = c2pa.data
  const hasSignature = !!manifest.c2pa_manifest?.signature
  const assertionsCount = manifest.c2pa_manifest?.assertions?.length ?? 0

  if (compact) {
    return (
      <span className={`c2pa-compact ${hasSignature ? 'valid' : 'partial'}`} title="C2PA 内容凭证">
        <BadgeCheck aria-hidden="true" />
        C2PA
      </span>
    )
  }

  return (
    <div className="c2pa-card">
      <div className="c2pa-header">
        <div className="c2pa-icon">
          <BadgeCheck aria-hidden="true" />
        </div>
        <div>
          <h3>C2PA 内容凭证</h3>
          <span className={`c2pa-status ${hasSignature ? 'valid' : 'partial'}`}>
            {hasSignature ? '已签名' : '未签名（仿真）'}
          </span>
        </div>
      </div>

      <div className="c2pa-body">
        <div className="c2pa-meta">
          <div>
            <span>凭证 ID</span>
            <strong className="hash-value">{manifest.passport_id}</strong>
          </div>
          <div>
            <span>模型</span>
            <strong>{manifest.model_id}</strong>
          </div>
          <div>
            <span>签发时间</span>
            <strong>{formatDateTime(manifest.created_at)}</strong>
          </div>
        </div>

        <div className="c2pa-metrics">
          <div className="c2pa-metric">
            <span>输入 Token</span>
            <strong>{formatNumber(manifest.input_tokens, 0)}</strong>
          </div>
          <div className="c2pa-metric">
            <span>输出 Token</span>
            <strong>{formatNumber(manifest.output_tokens, 0)}</strong>
          </div>
          <div className="c2pa-metric">
            <span>总 Token</span>
            <strong>{formatNumber(manifest.total_tokens, 0)}</strong>
          </div>
          <div className="c2pa-metric">
            <span>能耗</span>
            <strong>{formatNumber(manifest.energy_micro_wh / 1_000_000, 6)} Wh</strong>
          </div>
          <div className="c2pa-metric">
            <span>碳排</span>
            <strong>{formatNumber(manifest.carbon_micro_g / 1_000_000, 6)} gCO₂e</strong>
          </div>
          <div className="c2pa-metric">
            <span>断言数</span>
            <strong>{assertionsCount}</strong>
          </div>
        </div>

        {manifest.c2pa_manifest && (
          <div className="c2pa-manifest-info">
            <div>
              <span>声明生成器</span>
              <strong>{manifest.c2pa_manifest.claim_generator}</strong>
            </div>
            <div>
              <span>格式</span>
              <strong>{manifest.c2pa_manifest.format}</strong>
            </div>
            <div>
              <span>标题</span>
              <strong>{manifest.c2pa_manifest.title}</strong>
            </div>
          </div>
        )}

        <div className="c2pa-notice">
          <ShieldCheck aria-hidden="true" />
          <span>此 C2PA 凭证为仿真实现，不构成官方认证。用于演示内容来源追溯能力。</span>
        </div>
      </div>
    </div>
  )
}
