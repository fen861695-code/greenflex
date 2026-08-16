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
  // --- Energy data provenance (v2) ---
  energy_provenance_tier: string
  energy_confidence_bps: number
  energy_source_description: string
  // --- Carbon intensity source (v2) ---
  carbon_intensity_source?: string
  carbon_intensity_provenance?: Provenance
  carbon_intensity_g_per_kwh?: number
}

// ---------------------------------------------------------------------------
// RL Router types (v2)
// ---------------------------------------------------------------------------
export type RLMode = 'disabled' | 'shadow' | 'advisory' | 'autonomous'

export interface RLStatus {
  enabled: boolean
  mode?: RLMode
  session_state?: string
  policy_version?: string
  policy_initialized?: boolean
  total_updates?: number
  total_transitions?: number
  buffer_size?: number
  decision_log_size?: number
  recent_agreement_rate?: number
  temperature?: number
  candidate_models?: string[]
  recent_rewards?: number[]
  recent_policy_losses?: number[]
  message?: string
}

export interface RLDecision {
  timestamp: string
  request_hash: string
  recommended_model: string
  baseline_model: string
  reward: number | null
  mode: string
}

export interface RLTrainResult {
  status: string
  collected: number
  required: number
  loss?: number
  reward_mean?: number
}

// ---------------------------------------------------------------------------
// C2PA types (v2)
// ---------------------------------------------------------------------------
export interface C2PAManifest {
  passport_id: string
  model_id: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  energy_micro_wh: number
  carbon_micro_g: number
  order_id: string | null
  created_at: string
  c2pa_manifest?: {
    claim_generator: string
    format: string
    title: string
    assertions: Array<{
      label: string
      data: Record<string, unknown>
    }>
    signature?: string
  }
}

export interface C2PAVerifyResult {
  valid: boolean
  error?: string
  passport_id?: string
  signature_valid?: boolean
  assertions_count?: number
}

// ---------------------------------------------------------------------------
// EU AI Act Compliance types (v2)
// ---------------------------------------------------------------------------
export interface ComplianceHighSeverityIssue {
  article: string
  requirement: string
  status: string
}

export interface ComplianceSummary {
  total_checks: number
  compliant: number
  partial: number
  non_compliant: number
  not_applicable: number
  applicable_checks: number
  compliance_score_percent: number
  risk_level: string
  high_severity_issues_count: number
  high_severity_issues: ComplianceHighSeverityIssue[]
  overall_status: string
}

export interface CompliancePlatformInfo {
  version: string
  deployment_type: string
  api_bound: string
  user_authentication: boolean
  audit_logging: boolean
  content_purge: boolean
  c2pa_support: boolean
  energy_reporting: boolean
  carbon_reporting: boolean
}

export interface ComplianceCheck {
  article: string
  requirement: string
  status: 'compliant' | 'partial' | 'non_compliant' | 'not_applicable'
  evidence: string
  recommendation?: string
}

export interface ComplianceReport {
  report_id: string
  generated_at: string
  regulation: string
  report_version: string
  summary: ComplianceSummary
  model_info: Record<string, unknown> | null
  platform_info: CompliancePlatformInfo
  checks: ComplianceCheck[]
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

// ---------------------------------------------------------------------------
// Unified Solution types (one-stop: input → auto-detect → priced options)
// ---------------------------------------------------------------------------

export type OutputLength = 'short' | 'medium' | 'long'
export type ComplexityLevel = 'low' | 'medium' | 'high'

export interface SolutionOption {
  rank: number
  is_recommended: boolean
  model_id: string
  model_name: string
  tier: ModelTier
  quality_risk: QualityRiskLevel
  complexity_level: ComplexityLevel
  detected_task_type: TaskType
  task_classification_confidence_bps: number | null
  estimated_input_tokens: number
  estimated_output_tokens: number
  item_count: number
  quote_id: string
  execution_mode: string
  total_price_rmb: string
  base_price_rmb: string
  discount_percent: string
  facility_energy_wh_est: string
  carbon_g_est: string
  renewable_share_percent: string
  estimated_execution_seconds: number
  estimated_wait_seconds: number
  scheduled_start: string
  scheduled_end: string
  expires_at: string
  reason_codes: string[]
  reason_summary: string
  confidence_bps: number
  confidence_label: string
  pricing_version: string
  signal_version: string
  energy_provenance_tier: string
  energy_confidence_bps: number
  carbon_intensity_source: string
  carbon_intensity_g_per_kwh: number
}

export interface SolutionResponse {
  solution_id: string
  detected_task_type: TaskType
  task_classification_confidence_bps: number | null
  complexity_level: ComplexityLevel
  estimated_input_tokens: number
  estimated_output_tokens: number
  item_count: number
  options: SolutionOption[]
  policy_version: string
  profile_version: string
}
