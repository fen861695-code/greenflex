import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, FilePlus2, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type OrderView } from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { formatDateTime, formatRmb, formatStatus, statusTone } from '../utils/format'

const filters = [
  { value: 'all', label: '全部' },
  { value: 'active', label: '进行中' },
  { value: 'completed', label: '已结束' },
] as const

export function OrdersPage() {
  const [filter, setFilter] = useState<(typeof filters)[number]['value']>('all')
  const orders = useQuery({
    queryKey: ['orders'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/orders')
      if (error) throw new Error('订单接口返回错误。')
      return data
    },
    refetchInterval: (query) => query.state.data?.some(isActive) ? 2_000 : false,
  })
  const visible = orders.data?.filter((order) => {
    if (filter === 'active') return isActive(order)
    if (filter === 'completed') return !isActive(order)
    return true
  })

  return (
    <main className="page">
      <PageHeader
        eyebrow="执行队列"
        title="推理订单"
        actions={<>
          <button className="icon-button" onClick={() => void orders.refetch()} title="刷新订单"><RefreshCw aria-hidden="true" /></button>
          <Link className="button primary" to="/orders/new"><FilePlus2 aria-hidden="true" />批量下单</Link>
        </>}
      />
      <div className="toolbar">
        <div className="segmented filter-tabs">
          {filters.map((item) => <button key={item.value} className={filter === item.value ? 'active' : ''} onClick={() => setFilter(item.value)}>{item.label}</button>)}
        </div>
        <span className="record-count">{visible?.length ?? 0} 个订单</span>
      </div>
      {orders.isLoading && <LoadingState label="读取订单" />}
      {orders.isError && <ErrorState message="订单列表暂时不可用。" />}
      {visible && visible.length === 0 && <div className="empty-state"><FilePlus2 aria-hidden="true" /><strong>暂无订单</strong><Link to="/">创建第一笔订单</Link></div>}
      {visible && visible.length > 0 && (
        <div className="table-wrap">
          <table className="data-table orders-table">
            <thead><tr><th>订单</th><th>状态</th><th>模型</th><th>执行方式</th><th>任务</th><th>金额</th><th>计划时间</th><th><span className="sr-only">查看</span></th></tr></thead>
            <tbody>{visible.map((order) => (
              <tr key={order.id}>
                <td><Link className="order-id" to={`/orders/${order.id}`}>{order.id.slice(0, 8)}</Link><small>{formatDateTime(order.created_at)}</small></td>
                <td><span className={`badge ${statusTone(order.status)}`}>{formatStatus(order.status)}</span></td>
                <td>{order.model_name}</td>
                <td>{order.execution_mode === 'flexible' ? '弹性' : '立即'}</td>
                <td>{order.succeeded_count + order.failed_count}/{order.item_count}</td>
                <td>{formatRmb(order.actual_price_rmb ?? order.quoted_price_rmb)}<small>{order.actual_price_rmb ? '实际' : '报价'}</small></td>
                <td>{formatDateTime(order.scheduled_start)}</td>
                <td><Link className="icon-button small" to={`/orders/${order.id}`} title="查看订单"><ArrowUpRight aria-hidden="true" /></Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </main>
  )
}

function isActive(order: OrderView): boolean {
  return ['queued', 'scheduled', 'running'].includes(order.status)
}
