import { useMutation, useQuery } from '@tanstack/react-query'
import { Brain, Calculator, Clock3, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import {
  api,
  apiMessage,
  type ModelTier,
  type QuoteOption,
  type RecommendationMode,
  type RecommendationResponse,
  type TaskType,
  type QualityRequirement,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { RecommendationCard } from '../components/RecommendationCard'
import { QuoteOptions } from '../components/QuoteOptions'

type WorkspaceForm = {
  prompt: string
  systemPrompt: string
  maxOutputTokens: number
  mode: RecommendationMode
  tier: ModelTier
  modelId: string
  useExactModel: boolean
  flexible: boolean
  deadline: string
  taskType: TaskType
  qualityRequirement: QualityRequirement
}

function defaultDeadline(): string {
  const date = new Date(Date.now() + 4 * 60 * 60 * 1_000)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function estimateTokens(text: string): number {
  return Math.max(1, Math.ceil(text.length / 3))
}

export function WorkspacePage() {
  const navigate = useNavigate()
  const [quotes, setQuotes] = useState<QuoteOption[]>([])
  const [quoteError, setQuoteError] = useState<string | null>(null)
  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null)
  const [showRecommendation, setShowRecommendation] = useState(false)

  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/models')
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })

  const { register, handleSubmit, watch, setValue } = useForm<WorkspaceForm>({
    defaultValues: {
      prompt: '',
      systemPrompt: '',
      maxOutputTokens: 256,
      mode: 'smart',
      tier: 'balanced',
      modelId: 'qwen2.5-1.5b-q4',
      useExactModel: false,
      flexible: false,
      deadline: defaultDeadline(),
      taskType: 'auto',
      qualityRequirement: 'standard',
    },
  })

  const mode = watch('mode')
  const useExactModel = watch('useExactModel')
  const flexible = watch('flexible')
  const promptValue = watch('prompt')

  const recommendationMutation = useMutation({
    mutationFn: async (values: WorkspaceForm) => {
      const body = {
        mode: values.mode,
        task_type: values.taskType,
        prompt_preview: values.prompt.slice(0, 512),
        estimated_input_tokens: estimateTokens(values.prompt),
        estimated_output_tokens: values.maxOutputTokens,
        item_count: 1,
        quality_requirement: values.qualityRequirement,
        deadline: values.flexible ? new Date(values.deadline).toISOString() : null,
        execution_mode: values.flexible ? 'flexible' : 'immediate',
      }
      const { data, error } = await api.POST('/api/v1/recommendations', { body })
      if (error) throw new Error(apiMessage(error))
      return data as RecommendationResponse
    },
    onSuccess: (rec) => {
      setRecommendation(rec)
      setShowRecommendation(true)
      setQuoteError(null)
    },
    onError: (error) => setQuoteError(apiMessage(error)),
  })

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
      setShowRecommendation(false)
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

  const handleAcceptRecommendation = () => {
    if (!recommendation) return
    setValue('useExactModel', true)
    setValue('modelId', recommendation.recommended_model_id)
    setShowRecommendation(false)
    // Now get quotes with the recommended model
    handleSubmit((values) => quoteMutation.mutate({ ...values, useExactModel: true, modelId: recommendation.recommended_model_id }))()
  }

  const handleRejectRecommendation = () => {
    setShowRecommendation(false)
    setValue('mode', 'manual')
  }

  const onSubmit = (values: WorkspaceForm) => {
    if (values.mode === 'smart' || values.mode === 'economy' || values.mode === 'quality') {
      recommendationMutation.mutate(values)
    } else {
      quoteMutation.mutate(values)
    }
  }

  return (
    <main className="page">
      <PageHeader
        eyebrow="用户工作台"
        title="创建绿色推理订单"
        actions={<ProvenanceBadge value="simulated" detail="当前价格和能源信号均为仿真" />}
      />

      <form className="workspace-form" onSubmit={handleSubmit(onSubmit)}>
        <section className="form-main">
          <label className="field grow">
            <span>任务文本</span>
            <textarea
              {...register('prompt', { required: true, maxLength: 8192 })}
              rows={11}
              placeholder="输入待处理文本"
            />
            <small>{promptValue.length.toLocaleString()} / 8,192 · 约 {estimateTokens(promptValue).toLocaleString()} tokens</small>
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
            <div className="field-heading"><Brain aria-hidden="true" /><span>路由模式</span></div>
            <div className="segmented four">
              <label><input type="radio" value="smart" {...register('mode')} /><span>智能</span></label>
              <label><input type="radio" value="economy" {...register('mode')} /><span>经济</span></label>
              <label><input type="radio" value="quality" {...register('mode')} /><span>高质量</span></label>
              <label><input type="radio" value="manual" {...register('mode')} /><span>手动</span></label>
            </div>
            {mode !== 'manual' && (
              <p className="mode-hint">
                {mode === 'smart' && 'GreenRouter 自动在质量、成本和能耗间平衡'}
                {mode === 'economy' && '优先选择低成本、低能耗模型'}
                {mode === 'quality' && '优先保证输出质量，使用高质量模型'}
              </p>
            )}
          </div>

          {mode === 'manual' && (
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
          )}

          {mode !== 'manual' && (
            <div className="settings-block">
              <div className="field-heading"><ShieldCheck aria-hidden="true" /><span>质量要求</span></div>
              <select {...register('qualityRequirement')}>
                <option value="minimum">最低（简单分类/抽取）</option>
                <option value="standard">标准（日常任务）</option>
                <option value="high">较高（重要内容）</option>
                <option value="critical">关键（代码/分析）</option>
              </select>
              <label className="field" style={{ marginTop: '0.5rem' }}>
                <span>任务类型</span>
                <select {...register('taskType')}>
                  <option value="auto">自动检测</option>
                  <option value="classification">分类</option>
                  <option value="extraction">信息抽取</option>
                  <option value="summarization">摘要</option>
                  <option value="generation">内容生成</option>
                  <option value="analysis">分析推理</option>
                  <option value="code">代码</option>
                </select>
              </label>
            </div>
          )}

          <div className="settings-block">
            <div className="field-heading"><Clock3 aria-hidden="true" /><span>执行时间</span></div>
            <label className="check-row">
              <input type="checkbox" {...register('flexible')} />
              <span>截止时间前弹性执行</span>
            </label>
            {flexible && <label className="field"><span>最晚完成时间</span><input type="datetime-local" {...register('deadline', { required: true })} /></label>}
          </div>

          <label className="field compact"><span>最大输出 Token</span><input type="number" min="16" max="512" step="16" {...register('maxOutputTokens', { valueAsNumber: true })} /></label>

          <button className="button primary full" type="submit" disabled={quoteMutation.isPending || recommendationMutation.isPending}>
            <Calculator aria-hidden="true" />
            {recommendationMutation.isPending
              ? '正在推荐...'
              : quoteMutation.isPending
                ? '正在计算报价...'
                : mode === 'manual'
                  ? '获取报价'
                  : '获取智能推荐'}
          </button>

          <div className="truth-strip">
            <span>模型输出与 Token</span><ProvenanceBadge value="measured" />
            <span>推荐与碳信号</span><ProvenanceBadge value="simulated" />
          </div>
        </aside>
      </form>

      {models.isError && <ErrorState message="模型目录暂时不可用。" />}
      {quoteError && <ErrorState message={quoteError} />}

      {showRecommendation && recommendation && (
        <RecommendationCard
          recommendation={recommendation}
          onAccept={handleAcceptRecommendation}
          onReject={handleRejectRecommendation}
          loading={quoteMutation.isPending}
        />
      )}

      <QuoteOptions
        options={quotes}
        onSelect={(quote) => orderMutation.mutate(quote)}
        pendingQuoteId={orderMutation.isPending ? orderMutation.variables?.quote_id : undefined}
      />
    </main>
  )
}
