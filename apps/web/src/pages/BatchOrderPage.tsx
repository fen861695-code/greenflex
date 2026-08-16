import { useMutation, useQuery } from '@tanstack/react-query'
import { FileJson2, FileUp, Leaf, Upload, ArrowRight } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'

import { api, apiMessage, type CarbonCalendarData, type ModelTier, type QuoteOption } from '../api/client'
import { ErrorState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { QuoteOptions } from '../components/QuoteOptions'
import { formatNumber } from '../utils/format'

type BatchForm = {
  file: FileList
  tier: ModelTier
  modelId: string
  useExactModel: boolean
  flexible: boolean
  deadline: string
}

function deadlineDefault(): string {
  const date = new Date(Date.now() + 8 * 60 * 60 * 1_000)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

export function BatchOrderPage() {
  const navigate = useNavigate()
  const [quotes, setQuotes] = useState<QuoteOption[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/models')
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })
  const { register, handleSubmit, watch } = useForm<BatchForm>({
    defaultValues: {
      tier: 'balanced',
      modelId: 'qwen2.5-1.5b-q4',
      useExactModel: false,
      flexible: true,
      deadline: deadlineDefault(),
    },
  })
  const selectedFile = watch('file')?.[0]
  const useExactModel = watch('useExactModel')
  const flexible = watch('flexible')

  const carbonHint = useQuery({
    queryKey: ['carbon-hint'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/signals/calendar', {
        params: { query: { days: 7 } },
      })
      if (error) throw new Error(apiMessage(error))
      return data as CarbonCalendarData
    },
    enabled: flexible,
  })

  const bestGreenTime = (() => {
    if (!carbonHint.data) return null
    const all = carbonHint.data.days.flatMap((d) => d.hours.map((h) => ({ ...h, date: d.date })))
    const best = all.reduce((a, b) => (a.carbon_g_per_kwh < b.carbon_g_per_kwh ? a : b))
    const worst = all.reduce((a, b) => (a.carbon_g_per_kwh > b.carbon_g_per_kwh ? a : b))
    const saving = worst.carbon_g_per_kwh > 0
      ? Math.round((1 - best.carbon_g_per_kwh / worst.carbon_g_per_kwh) * 100)
      : 0
    return { best, saving }
  })()

  const quoteMutation = useMutation({
    mutationFn: async (values: BatchForm) => {
      const file = values.file[0]
      if (!file) throw new Error('请选择 CSV 或 JSONL 文件。')
      const form = new FormData()
      form.append('file', file, file.name)
      if (values.useExactModel) form.append('model_id', values.modelId)
      else form.append('tier', values.tier)
      if (values.flexible) form.append('deadline', new Date(values.deadline).toISOString())
      const response = await fetch('/api/v1/quotes/upload', { method: 'POST', body: form })
      const payload: unknown = await response.json()
      if (!response.ok) throw new Error(apiMessage(payload))
      if (!isQuoteResponse(payload)) throw new Error('报价接口返回格式无效。')
      return payload.options
    },
    onSuccess: (options) => {
      setMessage(null)
      setQuotes(options)
    },
    onError: (error) => setMessage(apiMessage(error)),
  })
  const orderMutation = useMutation({
    mutationFn: async (quote: QuoteOption) => {
      const { data, error } = await api.POST('/api/v1/orders', { body: { quote_id: quote.quote_id } })
      if (error) throw new Error(apiMessage(error))
      return data
    },
    onSuccess: (order) => navigate(`/orders/${order.id}`),
    onError: (error) => setMessage(apiMessage(error)),
  })

  return (
    <main className="page">
      <PageHeader
        eyebrow="批量任务"
        title="上传推理订单"
        actions={<ProvenanceBadge value="simulated" detail="报价与调度信号为仿真" />}
      />
      <form className="batch-form" onSubmit={handleSubmit((values) => quoteMutation.mutate(values))}>
        <section className="upload-zone">
          <input
            id="batch-file"
            type="file"
            accept=".csv,.jsonl,text/csv,application/x-ndjson"
            {...register('file', { required: true })}
          />
          <label htmlFor="batch-file">
            <span className="upload-icon"><FileUp aria-hidden="true" /></span>
            <strong>{selectedFile ? selectedFile.name : '选择 CSV 或 JSONL'}</strong>
            <small>{selectedFile ? `${formatNumber(selectedFile.size / 1024, 1)} KB` : 'UTF-8 · 最大 5MB · 最多 500 条'}</small>
          </label>
          <div className="schema-line"><FileJson2 aria-hidden="true" /><code>client_item_id, prompt, system_prompt, max_output_tokens</code></div>
        </section>
        <aside className="batch-settings">
          <fieldset className="field-group">
            <legend>模型档位</legend>
            <div className="segmented three">
              <label><input type="radio" value="economy" {...register('tier')} disabled={useExactModel} /><span>经济</span></label>
              <label><input type="radio" value="balanced" {...register('tier')} disabled={useExactModel} /><span>标准</span></label>
              <label><input type="radio" value="quality" {...register('tier')} disabled={useExactModel} /><span>高质量</span></label>
            </div>
          </fieldset>
          <label className="check-row"><input type="checkbox" {...register('useExactModel')} /><span>高级模型自选</span></label>
          {useExactModel && (
            <label className="field"><span>本地模型</span><select {...register('modelId')}>
              {models.data?.map((model) => <option key={model.id} value={model.id}>{model.display_name}{model.available ? '' : '（不可用）'}</option>)}
            </select></label>
          )}
          <label className="check-row"><input type="checkbox" {...register('flexible')} /><span>截止时间前弹性执行</span></label>
          {flexible && <label className="field"><span>最晚完成时间</span><input type="datetime-local" {...register('deadline', { required: true })} /></label>}
          <button className="button primary full" type="submit" disabled={quoteMutation.isPending}>
            <Upload aria-hidden="true" />{quoteMutation.isPending ? '正在解析' : '解析并报价'}
          </button>
        </aside>
      </form>
      {flexible && bestGreenTime && (
        <Link to="/carbon" className="carbon-hint-banner">
          <div className="carbon-hint-icon"><Leaf size={16} /></div>
          <div className="carbon-hint-text">
            <strong>绿色调度已开启</strong>
            <span>
              最清洁时段 {bestGreenTime.best.date.slice(5)} {String(bestGreenTime.best.hour).padStart(2, '0')}:00
              （{bestGreenTime.best.carbon_g_per_kwh} g/kWh），比高峰时段省 {bestGreenTime.saving}% 碳排放。
              查看完整碳信号地图 →
            </span>
          </div>
          <ArrowRight size={16} className="carbon-hint-arrow" />
        </Link>
      )}
      {message && <ErrorState message={message} />}
      <QuoteOptions
        options={quotes}
        onSelect={(quote) => orderMutation.mutate(quote)}
        pendingQuoteId={orderMutation.isPending ? orderMutation.variables?.quote_id : undefined}
      />
    </main>
  )
}

function isQuoteResponse(value: unknown): value is { options: QuoteOption[] } {
  return typeof value === 'object' && value !== null && 'options' in value && Array.isArray(value.options)
}
