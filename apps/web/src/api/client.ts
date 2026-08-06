import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  fetch: (request) => globalThis.fetch(request),
})

export type ModelCatalogItem = components['schemas']['ModelCatalogItem'] & {
  estimated_tokens_per_second?: number
  energy_wh_per_1k_output?: string
  carbon_g_per_1k_output?: string
  is_cloud_model?: boolean
  energy_provenance?: string
}
export type ModelTier = components['schemas']['ModelTier']
export type OrderView = components['schemas']['OrderView']
export type PassportView = components['schemas']['PassportView']
export type PreviewResponse = components['schemas']['PreviewResponse']
export type Provenance = components['schemas']['Provenance']
export type QuoteOption = components['schemas']['QuoteOption']

// GreenRouter v1 types
export type RecommendationMode = 'smart' | 'economy' | 'quality' | 'manual'
export type QualityRiskLevel = 'low' | 'medium' | 'high' | 'very_high'
export type TaskType =
  | 'classification'
  | 'extraction'
  | 'summarization'
  | 'analysis'
  | 'generation'
  | 'code'
  | 'auto'
export type QualityRequirement = 'minimum' | 'standard' | 'high' | 'critical'

export interface RecommendationAlternative {
  model_id: string
  model_name: string
  tier: ModelTier
  quality_risk: QualityRiskLevel
  estimated_price_rmb: string
  estimated_energy_wh: string
  estimated_carbon_g: string
  estimated_execution_seconds: number
  estimated_wait_seconds: number
  price_diff_pct: string
  energy_diff_pct: string
  reason_codes: string[]
}

export interface RecommendationResponse {
  recommendation_id: string
  recommended_model_id: string
  recommended_model_name: string
  recommended_tier: ModelTier
  recommended_mode: RecommendationMode
  recommended_execution_mode: string
  quality_risk: QualityRiskLevel
  confidence_bps: number
  confidence_label: string
  estimated_price_rmb: string
  estimated_energy_wh: string
  estimated_carbon_g: string
  estimated_execution_seconds: number
  estimated_wait_seconds: number
  reason_codes: string[]
  reason_summary: string
  alternatives: RecommendationAlternative[]
  policy_version: string
  profile_version: string
  provenance: Provenance
  shadow_mode: boolean
}

export function apiMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null) {
    if ('message' in error && typeof error.message === 'string') {
      return error.message
    }
    if ('detail' in error && Array.isArray(error.detail)) {
      return '提交内容不符合接口约束，请检查字段和长度。'
    }
  }
  return '请求未完成，请确认本地 API 正在运行。'
}
