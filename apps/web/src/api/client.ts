import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

const ADMIN_TOKEN_KEY = 'greenflex_admin_token'

export function getAdminToken(): string {
  return sessionStorage.getItem(ADMIN_TOKEN_KEY) ?? ''
}

export function setAdminToken(token: string): void {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token)
}

export function clearAdminToken(): void {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY)
}

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  fetch: (request) => {
    const token = getAdminToken()
    if (token) {
      request.headers.set('X-Admin-Token', token)
    }
    return globalThis.fetch(request)
  },
})

export type ModelCatalogItem = components['schemas']['ModelCatalogItem'] & {
  estimated_tokens_per_second?: number
  energy_wh_per_1k_output?: string
  carbon_g_per_1k_output?: string
  is_cloud_model?: boolean
  energy_provenance?: string
  recommended_batch_size?: number
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

export interface TaskUnderstanding {
  task_type: string
  task_type_label: string
  complexity: string
  complexity_label: string
  estimated_input_tokens: number
  estimated_output_tokens: number
  estimated_item_count: number
  output_length_hint: string
  requires_json: boolean
  recommended_tier: string
  confidence_bps: number
  confidence_label: string
  detected_intents: string[]
  reasoning: string
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
  task_understanding: TaskUnderstanding | null
  policy_version: string
  profile_version: string
  provenance: Provenance
  shadow_mode: boolean
}

export interface CarbonCalendarHour {
  hour: number
  carbon_g_per_kwh: number
  price_micro_rmb_per_kwh: number
  renewable_share_bps: number
}

export interface CarbonCalendarDay {
  date: string
  hours: CarbonCalendarHour[]
}

export interface CarbonCalendarResponse {
  region: string
  signal_version: string
  days: CarbonCalendarDay[]
}

export type CarbonCalendarData = CarbonCalendarResponse

// Chat types
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatResponse {
  model_id: string
  model_name: string
  reply: string
  prompt_tokens: number
  completion_tokens: number
  duration_ms: number
  estimated_price_micro_rmb: number
  estimated_energy_micro_wh: number
  estimated_carbon_micro_g: number
  inference_source: string
}

export interface CloudApiProviderStatus {
  provider: string
  label: string
  configured: boolean
  key_preview: string | null
  default_base_url: string
}

export interface CloudApiSettings {
  providers: CloudApiProviderStatus[]
  timeout_seconds: number
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
