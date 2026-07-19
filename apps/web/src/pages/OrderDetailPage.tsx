import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, Download, Eraser, FileBadge2, RefreshCw } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { api, apiMessage, type OrderView } from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { formatDateTime, formatNumber, formatRmb, formatStatus, statusTone } from '../utils/format'

export function OrderDetailPage() {
  const { id = '' } = useParams()
  const queryClient = useQueryClient()
  const order = useQuery({
    queryKey: ['order', id],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/orders/{order_id}', { params: { path: { order_id: id } } })
      if (error) throw new Error(apiMessage(error))
      return data
    },
    enabled: id.length > 0,
    refetchInterval: (query) => query.state.data && isActive(query.state.data) ? 1_500 : false,
  })
  const action = useMutation({
    mutationFn: async (kind: 'cancel' | 'purge') => {
      if (kind === 'cancel') {
        const { error } = await api.POST('/api/v1/orders/{order_id}/cancel', { params: { path: { order_id: id } } })
        if (error) throw new Error(apiMessage(error))
      } else {
        const { error } = await api.DELETE('/api/v1/orders/{order_id}/content', { params: { path: { order_id: id } } })
        if (error) throw new Error(apiMessage(error))
      }
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['order', id] }),
  })
  const data = order.data

  if (order.isLoading) return <main className="page"><LoadingState label="读取订单详情" /></main>
  if (order.isError || !data) return <main className="page"><ErrorState message={apiMessage(order.error)} /></main>
  const terminal = !isActive(data)
  return (
    <main className="page">
      <PageHeader
        eyebrow={`订单 ${data.id.slice(0, 8)}`}
        title={data.model_name}
        actions={<>
          <span className={`badge ${statusTone(data.status)}`}>{formatStatus(data.status)}</span>
          <button className="icon-button" onClick={() => void order.refetch()} title="刷新"><RefreshCw aria-hidden="true" /></button>
        </>}
      />
      {action.isError && <ErrorState message={apiMessage(action.error)} />}
      <section className="summary-band">
        <div><span>执行进度</span><strong>{data.succeeded_count + data.failed_count} / {data.item_count}</strong><small>{data.failed_count} 条失败</small></div>
        <div><span>实际账单</span><strong>{formatRmb(data.actual_price_rmb)}</strong><small>报价 {formatRmb(data.quoted_price_rmb)} <ProvenanceBadge value="simulated" /></small></div>
        <div><span>GPU 总能耗</span><strong>{formatNumber(data.gross_gpu_energy_wh, 6)} Wh</strong><small><ProvenanceBadge value={data.completed_at ? 'measured' : 'estimated'} /></small></div>
        <div><span>位置法碳排</span><strong>{formatNumber(data.location_carbon_g, 6)} g</strong><small><ProvenanceBadge value="estimated" /></small></div>
      </section>
      <section className="order-timeline">
        <div><span>创建</span><strong>{formatDateTime(data.created_at)}</strong></div>
        <div><span>计划</span><strong>{formatDateTime(data.scheduled_start)}</strong></div>
        <div><span>开始</span><strong>{formatDateTime(data.started_at)}</strong></div>
        <div><span>完成</span><strong>{formatDateTime(data.completed_at)}</strong></div>
      </section>
      <div className="action-bar">
        {['queued', 'scheduled'].includes(data.status) && <button className="button danger-outline" onClick={() => action.mutate('cancel')} disabled={action.isPending}><Ban aria-hidden="true" />取消订单</button>}
        {terminal && <a className="button secondary" href={`/api/v1/orders/${id}/results`}><Download aria-hidden="true" />下载结果 CSV</a>}
        {terminal && <Link className="button secondary" to={`/passports/${id}`}><FileBadge2 aria-hidden="true" />Token Passport</Link>}
        {terminal && !data.content_purged && <button className="icon-button danger-text" title="清除原文和输出" onClick={() => { if (window.confirm('清除后无法恢复原文和模型输出，继续吗？')) action.mutate('purge') }}><Eraser aria-hidden="true" /></button>}
      </div>
      <section className="items-section">
        <div className="section-heading"><div><p className="eyebrow">逐项结果</p><h2>任务明细</h2></div>{data.content_purged && <span className="badge neutral">内容已清除</span>}</div>
        <div className="table-wrap"><table className="data-table items-table">
          <thead><tr><th>任务 ID</th><th>状态</th><th>Token</th><th>耗时</th><th>结果 / 错误</th></tr></thead>
          <tbody>{data.items?.map((item) => <tr key={item.client_item_id}>
            <td><code>{item.client_item_id}</code></td>
            <td><span className={`badge ${statusTone(item.status)}`}>{formatStatus(item.status)}</span></td>
            <td>{item.output_tokens ?? '—'}<small>输出</small></td>
            <td>{formatNumber(item.duration_ms, 1)} ms</td>
            <td className="result-cell">{item.output ?? item.error_code ?? '—'}</td>
          </tr>)}</tbody>
        </table></div>
      </section>
    </main>
  )
}

function isActive(order: OrderView): boolean {
  return ['queued', 'scheduled', 'running'].includes(order.status)
}
