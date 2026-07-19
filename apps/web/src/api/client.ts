import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  fetch: (request) => globalThis.fetch(request),
})

export type ModelCatalogItem = components['schemas']['ModelCatalogItem']
export type ModelTier = components['schemas']['ModelTier']
export type OrderView = components['schemas']['OrderView']
export type PassportView = components['schemas']['PassportView']
export type PreviewResponse = components['schemas']['PreviewResponse']
export type Provenance = components['schemas']['Provenance']
export type QuoteOption = components['schemas']['QuoteOption']

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
