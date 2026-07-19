import { useMutation, useQuery } from '@tanstack/react-query'
import { Calculator, Clock3, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

import { api, apiMessage, type ModelTier, type QuoteOption } from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { QuoteOptions } from '../components/QuoteOptions'

type WorkspaceForm = {
  prompt: string
  systemPrompt: string
  maxOutputTokens: number
  tier: ModelTier
  modelId: string
  useExactModel: boolean
  flexible: boolean
  deadline: string
}

function defaultDeadline(): string {
  const date = new Date(Date.now() + 4 * 60 * 60 * 1_000)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export function WorkspacePage() {
  const navigate = useNavigate()
  const [quotes, setQuotes] = useState<QuoteOption[]>([])
  const [quoteError, setQuoteError] = useState<string | null>(null)
  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/models')
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })
  const { register, handleSubmit, watch } = useForm<WorkspaceForm>({
    defaultValues: {
      prompt: '',
      systemPrompt: '',
      maxOutputTokens: 256,
      tier: 'balanced',
      modelId: 'qwen2.5-1.5b-q4',
      useExactModel: false,
      flexible: false,
      deadline: defaultDeadline(),
    },
  })
  const useExactModel = watch('useExactModel')
  const flexible = watch('flexible')

  const quoteMutation = useMutation({
    mutationFn: async (values: WorkspaceForm) => {
      const body = {
        items: [
          {
            client_item_id: `manual-${crypto.randomUUID()}`,
            prompt: values.prompt,
            system_prompt: values.systemPrompt || null,
            max_output_tokens: values.maxOutputTokens,
          },
        ],
        model_id: values.useExactModel ? values.modelId : null,
        tier: values.useExactModel ? null : values.tier,
        deadline: values.flexible ? new Date(values.deadline).toISOString() : null,
      }
      const { data, error } = await api.POST('/api/v1/quotes', { body })
      if (error) throw new Error(apiMessage(error))
      return data.options
    },
    onSuccess: (options) => {
      setQuoteError(null)
      setQuotes(options)
    },
    onError: (error) => setQuoteError(apiMessage(error)),
  })
  const orderMutation = useMutation({
    mutationFn: async (quote: QuoteOption) => {
      const { data, error } = await api.POST('/api/v1/orders', {
        body: { quote_id: quote.quote_id },
      })
      if (error) throw new Error(apiMessage(error))
      return data
    },
    onSuccess: (order) => navigate(`/orders/${order.id}`),
    onError: (error) => setQuoteError(apiMessage(error)),
  })

  return (
    <main className="page">
      <PageHeader
        eyebrow="用户工作台"
        title="创建绿色推理订单"
        actions={<ProvenanceBadge value="simulated" detail="当前价格和能源信号均为仿真" />}
      />
      <form className="workspace-form" onSubmit={handleSubmit((values) => quoteMutation.mutate(values))}>
        <section className="form-main">
          <label className="field grow">
            <span>任务文本</span>
            <textarea
              {...register('prompt', { required: true, maxLength: 8192 })}
              rows={11}
              placeholder="输入待处理文本"
            />
            <small>{watch('prompt').length.toLocaleString()} / 8,192</small>
          </label>
          <details className="advanced-fields">
            <summary>系统提示词</summary>
            <label className="field">
              <span className="sr-only">系统提示词</span>
              <textarea {...register('systemPrompt', { maxLength: 4096 })} rows={3} />
            </label>
          </details>
        </section>
        <aside className="order-settings">
          <div className="settings-block">
            <div className="field-heading"><Sparkles aria-hidden="true" /><span>模型档位</span></div>
            <div className="segmented three">
              <label><input type="radio" value="economy" {...register('tier')} disabled={useExactModel} /><span>经济</span></label>
              <label><input type="radio" value="balanced" {...register('tier')} disabled={useExactModel} /><span>标准</span></label>
              <label><input type="radio" value="quality" {...register('tier')} disabled={useExactModel} /><span>高质量</span></label>
            </div>
            <label className="check-row">
              <input type="checkbox" {...register('useExactModel')} />
              <span>高级模型自选</span>
            </label>
            {useExactModel && (
              <label className="field">
                <span>本地模型</span>
                {models.isLoading ? <LoadingState label="检测模型" /> : (
                  <select {...register('modelId')}>
                    {models.data?.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.display_name}{model.available ? '' : '（不可用）'}
                      </option>
                    ))}
                  </select>
                )}
              </label>
            )}
          </div>
          <div className="settings-block">
            <div className="field-heading"><Clock3 aria-hidden="true" /><span>执行时间</span></div>
            <label className="check-row">
              <input type="checkbox" {...register('flexible')} />
              <span>截止时间前弹性执行</span>
            </label>
            {flexible && <label className="field"><span>最晚完成时间</span><input type="datetime-local" {...register('deadline', { required: true })} /></label>}
          </div>
          <label className="field compact"><span>最大输出 Token</span><input type="number" min="16" max="512" step="16" {...register('maxOutputTokens', { valueAsNumber: true })} /></label>
          <button className="button primary full" type="submit" disabled={quoteMutation.isPending}>
            <Calculator aria-hidden="true" />
            {quoteMutation.isPending ? '正在计算' : '获取仿真报价'}
          </button>
          <div className="truth-strip"><span>模型输出与 Token</span><ProvenanceBadge value="measured" /><span>报价与碳信号</span><ProvenanceBadge value="simulated" /></div>
        </aside>
      </form>
      {models.isError && <ErrorState message="模型目录暂时不可用。" />}
      {quoteError && <ErrorState message={quoteError} />}
      <QuoteOptions
        options={quotes}
        onSelect={(quote) => orderMutation.mutate(quote)}
        pendingQuoteId={orderMutation.isPending ? orderMutation.variables?.quote_id : undefined}
      />
    </main>
  )
}
