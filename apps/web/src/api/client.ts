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
