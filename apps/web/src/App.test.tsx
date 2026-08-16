import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { App } from './App'
import type { ModelCatalogItem, OrderView, PassportView, QuoteOption } from './api/client'

const models: ModelCatalogItem[] = [
  {
    id: 'qwen2.5-0.5b-q4',
    display_name: 'Qwen2.5 0.5B',
    runtime_name: 'qwen2.5:0.5b',
    tier: 'economy',
    parameter_b: '0.5B',
    context_limit: 4096,
    recommended_for: ['分类'],
    input_rate_rmb_per_million: '0.100000',
    output_rate_rmb_per_million: '0.300000',
    available: true,
    availability_detail: '已安装 · sha256:fixture',
    rate_provenance: 'simulated',
  },
  {
    id: 'qwen2.5-1.5b-q4',
    display_name: 'Qwen2.5 1.5B',
    runtime_name: 'qwen2.5:1.5b',
    tier: 'balanced',
    parameter_b: '1.5B',
    context_limit: 4096,
    recommended_for: ['摘要'],
    input_rate_rmb_per_million: '0.300000',
    output_rate_rmb_per_million: '0.800000',
    available: true,
    availability_detail: '已安装 · sha256:fixture',
    rate_provenance: 'simulated',
  },
  {
    id: 'qwen2.5-3b-q4',
    display_name: 'Qwen2.5 3B',
    runtime_name: 'qwen2.5:3b',
    tier: 'quality',
    parameter_b: '3B',
    context_limit: 4096,
    recommended_for: ['分析'],
    input_rate_rmb_per_million: '0.600000',
    output_rate_rmb_per_million: '1.500000',
    available: true,
    availability_detail: '已安装 · sha256:fixture',
    rate_provenance: 'simulated',
  },
]

const quote: QuoteOption = {
  quote_id: 'quote-001',
  model_id: 'qwen2.5-1.5b-q4',
  model_name: 'Qwen2.5 1.5B',
  tier: 'balanced',
  execution_mode: 'immediate',
  item_count: 1,
  estimated_input_tokens: 12,
  estimated_output_tokens: 128,
  scheduled_start: '2026-07-19T09:00:00Z',
  scheduled_end: '2026-07-19T09:01:00Z',
  deadline: null,
  base_price_rmb: '0.000100',
  discount_percent: '0.00',
  discount_rmb: '0.000000',
  vpp_rebate_rmb: '0.000000',
  total_price_rmb: '0.000100',
  facility_energy_wh_est: '0.001200',
  carbon_g_est: '0.000600',
  renewable_share_percent: '45.00',
  pricing_version: 'pricing-sim-v1',
  signal_version: 'synthetic-cn-east-v1',
  commercial_provenance: 'simulated',
  environmental_provenance: 'simulated',
  expires_at: '2026-07-19T09:15:00Z',
}

const recommendation = {
  recommendation_id: 'rec-001',
  recommended_model_id: 'qwen2.5-1.5b-q4',
  recommended_model_name: 'Qwen2.5 1.5B',
  recommended_tier: 'balanced',
  recommended_mode: 'smart',
  recommended_execution_mode: 'immediate',
  quality_risk: 'low',
  confidence_bps: 8000,
  confidence_label: '高',
  estimated_price_rmb: '0.000100',
  estimated_energy_wh: '0.001200',
  estimated_carbon_g: '0.000600',
  estimated_execution_seconds: 3,
  estimated_wait_seconds: 0,
  reason_codes: ['balanced_choice'],
  reason_summary: '在质量与成本之间取得平衡',
  alternatives: [],
  policy_version: 'green-router-rule-v1',
  profile_version: 'model-task-profile-v1',
  provenance: 'estimated',
  shadow_mode: true,
}

const order: OrderView = {
  id: 'order-001',
  quote_id: 'quote-001',
  model_id: 'qwen2.5-1.5b-q4',
  model_name: 'Qwen2.5 1.5B',
  execution_mode: 'immediate',
  status: 'succeeded',
  scheduled_start: '2026-07-19T09:00:00Z',
  deadline: null,
  quoted_price_rmb: '0.000100',
  actual_price_rmb: '0.000090',
  item_count: 1,
  succeeded_count: 1,
  failed_count: 0,
  gross_gpu_energy_wh: '0.001000',
  incremental_gpu_energy_wh: '0.000500',
  location_carbon_g: '0.000600',
  content_purged: false,
  created_at: '2026-07-19T09:00:00Z',
  started_at: '2026-07-19T09:00:01Z',
  completed_at: '2026-07-19T09:00:02Z',
  items: [
    {
      client_item_id: 'item-001',
      status: 'succeeded',
      output: 'synthetic-result',
      prompt_tokens: 9,
      output_tokens: 13,
      duration_ms: '10.000',
      error_code: null,
    },
  ],
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('GreenFlex user flows', () => {
  it('submits a manual workload and renders a simulated quote', async () => {
    installFetch((request) => {
      if (request.method === 'GET' && pathOf(request) === '/api/v1/models') return json(models)
      if (request.method === 'POST' && pathOf(request) === '/api/v1/recommendations') return json(recommendation)
      if (request.method === 'POST' && pathOf(request) === '/api/v1/quotes') return json({ options: [quote] })
      if (request.method === 'POST' && pathOf(request) === '/api/v1/orders') return json(order)
      if (request.method === 'GET' && pathOf(request) === '/api/v1/orders/order-001') return json(order)
      return json({}, 404)
    })
    renderApp('/')
    expect(screen.getByRole('heading', { name: '创建绿色推理订单' })).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText('输入待处理文本'), { target: { value: 'synthetic-input' } })
    fireEvent.click(screen.getByRole('button', { name: '获取智能推荐' }))
    // Accept the recommendation to proceed to quotes
    fireEvent.click(await screen.findByRole('button', { name: '使用推荐模型' }))
    expect(await screen.findByRole('heading', { name: '选择执行方案' })).toBeInTheDocument()
    expect(screen.getByText('Qwen2.5 1.5B', { exact: false })).toBeInTheDocument()
    expect(screen.getAllByText('仿真').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByTitle('打开菜单'))
    expect(document.querySelector('.sidebar.open')).not.toBeNull()
    fireEvent.click(screen.getByTitle('关闭菜单'))
    fireEvent.click(screen.getByRole('button', { name: '接受报价' }))
    expect(await screen.findByText('synthetic-result')).toBeInTheDocument()
  })

  it('runs available preview models sequentially', async () => {
    installFetch(async (request) => {
      if (request.method === 'GET') return json(models.slice(0, 2))
      const body = await request.clone().json() as { model_id: string }
      return json({
        model_id: body.model_id,
        output: 'synthetic-result',
        prompt_tokens: 9,
        output_tokens: 13,
        latency_ms: '10.000',
        gross_gpu_energy_wh: '0.001000',
        incremental_gpu_energy_wh: '0.000500',
        telemetry_provenance: 'measured',
        telemetry_source: 'fixture',
      })
    })
    renderApp('/preview')
    fireEvent.change(await screen.findByPlaceholderText('输入同一段文本，按顺序对比所选模型'), { target: { value: 'synthetic-input' } })
    await waitFor(() => expect(screen.getByRole('button', { name: '运行 2 个模型' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '运行 2 个模型' }))
    expect((await screen.findAllByText('synthetic-result')).length).toBe(2)
    expect(screen.getByRole('heading', { name: '实测对比' })).toBeInTheDocument()
  })

  it('shows model-offline state without inventing measurements', async () => {
    installFetch(() => json(models.map((model) => ({ ...model, available: false }))))
    renderApp('/preview')
    expect(await screen.findByText(/未检测到可用模型/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '运行 0 个模型' })).toBeDisabled()
  })

  it('renders orders and completed order evidence', async () => {
    installFetch((request) => pathOf(request) === '/api/v1/orders' ? json([order]) : json(order))
    const view = renderApp('/orders')
    expect(await screen.findByText('order-00')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
    view.unmount()
    renderApp('/orders/order-001')
    expect(await screen.findByText('synthetic-result')).toBeInTheDocument()
    expect(screen.getByText('Token Passport')).toBeInTheDocument()
    expect(screen.getByText('下载结果 CSV')).toBeInTheDocument()
  })

  it('cancels active orders and purges completed content', async () => {
    let cancelled = false
    const activeOrder: OrderView = { ...order, status: 'queued', completed_at: null, items: [] }
    installFetch((request) => {
      if (request.method === 'POST') cancelled = true
      return json(activeOrder)
    })
    const activeView = renderApp('/orders/order-001')
    fireEvent.click(await screen.findByRole('button', { name: '取消订单' }))
    await waitFor(() => expect(cancelled).toBe(true))
    activeView.unmount()
    cleanup()

    let purged = false
    vi.stubGlobal('confirm', vi.fn(() => true))
    installFetch((request) => {
      if (request.method === 'DELETE') purged = true
      return json(order)
    })
    renderApp('/orders/order-001')
    fireEvent.click(await screen.findByTitle('清除原文和输出'))
    await waitFor(() => expect(purged).toBe(true))
  })

  it('renders a content-free Token Passport', async () => {
    const passport: PassportView = {
      passport_id: 'passport-001',
      order_id: 'order-001',
      payload_sha256: 'a'.repeat(64),
      created_at: '2026-07-19T09:00:02Z',
      payload: {
        model: { runtime_name: 'qwen2.5:1.5b', digest: 'sha256:fixture' },
        usage: { input_tokens: 9, output_tokens: 13 },
        gpu_energy: { gross_micro_wh: 1000, incremental_micro_wh: 500 },
        facility_energy: { micro_wh: 1200 },
        location_carbon: { micro_g_co2e: 600 },
        green_grade: { grade: 'B' },
        bill: { actual_micro_rmb: 90, discount_bps: 500, pricing_version: 'pricing-sim-v1' },
      },
    }
    installFetch(() => json(passport))
    renderApp('/passports/order-001')
    expect(await screen.findByRole('heading', { name: '仿真绿色等级 B' })).toBeInTheDocument()
    expect(screen.getByText('不包含原始提示词和输出')).toBeInTheDocument()
    expect(screen.getByText('不构成官方认证')).toBeInTheDocument()
  })

  it('accepts a structured batch file', () => {
    installFetch((request) => pathOf(request) === '/api/v1/models' ? json(models) : json({ options: [quote] }))
    renderApp('/orders/new')
    const file = new File(['client_item_id,prompt\nitem-001,synthetic-input'], 'batch.csv', { type: 'text/csv' })
    const input = document.getElementById('batch-file') as HTMLInputElement
    const files = { 0: file, length: 1, item: () => file }
    fireEvent.change(input, { target: { files } })
    expect(screen.getByText('batch.csv')).toBeInTheDocument()
    expect(screen.getByText(/client_item_id, prompt/)).toBeInTheDocument()
  })
})

function renderApp(route: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}><App /></MemoryRouter>
    </QueryClientProvider>,
  )
}

function installFetch(handler: (request: Request) => Response | Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request
      ? input
      : new Request(new URL(String(input), window.location.origin), {
          method: init?.method,
          headers: init?.headers,
        })
    return handler(request)
  }))
}

function pathOf(request: Request): string {
  return new URL(request.url).pathname
}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
}
