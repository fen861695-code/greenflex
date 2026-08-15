import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Brain,
  Calculator,
  Clock3,
  Lightbulb,
  ShieldCheck,
  Sparkles,
  Tag,
  Zap,
  TrendingDown,
  ChevronDown,
  Settings2,
  Leaf,
  ArrowRight,
} from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import {
  api,
  apiMessage,
  type CarbonCalendarData,
  type ModelTier,
  type QuoteOption,
  type RecommendationMode,
  type RecommendationResponse,
  type TaskType,
  type QualityRequirement,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
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
  const date = new Date(Date.now() + 4 * 60 * 60 * 1000)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function estimateTokens(text: string): number {
  return Math.max(1, Math.ceil(text.length / 3))
}

const MODE_OPTIONS: {
  value: RecommendationMode
  label: string
  desc: string
  icon: typeof Brain
  color: string
}[] = [
  { value: 'smart', label: '智能推荐', desc: '自动平衡质量、成本和能耗', icon: Brain, color: '#1a8f5c' },
  { value: 'economy', label: '经济优先', desc: '最低成本和能耗', icon: TrendingDown, color: '#2e7e58' },
  { value: 'quality', label: '高质量优先', desc: '最强模型，最佳效果', icon: Sparkles, color: '#6d4aa0' },
  { value: 'manual', label: '手动选择', desc: '自己指定模型和档位', icon: Settings2, color: '#5f726b' },
]

export function WorkspacePage() {
  const navigate = useNavigate()
  const [quotes, setQuotes] = useState<QuoteOption[]>([])
  const [quoteError, setQuoteError] = useState<string | null>(null)
  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null)
  const [showRecommendation, setShowRecommendation] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/models')
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })

  const carbonHint = useQuery({
    queryKey: ['carbon-hint'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/signals/calendar', {
        params: { query: { days: 7 } },
      })
      if (error) throw new Error(apiMessage(error))
      return data as CarbonCalendarData
    },
  })

  const greenHint = (() => {
    if (!carbonHint.data) return null
    const all = carbonHint.data.days.flatMap((d) => d.hours.map((h) => ({ ...h, date: d.date })))
    const best = all.reduce((a, b) => (a.carbon_g_per_kwh < b.carbon_g_per_kwh ? a : b))
    const worst = all.reduce((a, b) => (a.carbon_g_per_kwh > b.carbon_g_per_kwh ? a : b))
    const saving = worst.carbon_g_per_kwh > 0
      ? Math.round((1 - best.carbon_g_per_kwh / worst.carbon_g_per_kwh) * 100)
      : 0
    return { best, saving }
  })()

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
        prompt_preview: values.prompt.slice(0, 4096),
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
      return data
    },
    onSuccess: (data) => setQuotes(data.options),
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
    void handleSubmit((values) => quoteMutation.mutate({ ...values, useExactModel: true, modelId: recommendation.recommended_model_id }))()
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

  const isPending = recommendationMutation.isPending || quoteMutation.isPending

  return (
    <main className="page workspace-page-v2">
      {/* Hero: task input */}
      <section className="hero-input">
        <div className="hero-badge">
          <Zap size={14} /> 绿色 AI 推理路由
        </div>
        <h1 className="hero-title">描述你的任务，<span className="hero-gradient">自动选模型</span></h1>
        <p className="hero-subtitle">
          不用懂 token、不用选模型——用自然语言说你要做什么，系统自动匹配质量够用、价格最低、碳排放最少的方案。
        </p>

        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="hero-textarea-wrap">
            <textarea
              {...register('prompt', { required: true, maxLength: 8192 })}
              rows={4}
              placeholder="例如：帮我把这些评论分一下好评和差评&#10;或：用 Python 写一个 MySQL 连接池工具类&#10;或：深度分析全球芯片产业链竞争格局，给董事会汇报"
              className="hero-textarea"
              autoFocus
            />
            <div className="hero-textarea-footer">
              <span className="hero-token-count">
                {promptValue.length.toLocaleString()} 字 · 约 {estimateTokens(promptValue).toLocaleString()} tokens
              </span>
              <button className="button primary hero-submit" type="submit" disabled={isPending || !promptValue.trim()}>
                <Calculator size={17} />
                {recommendationMutation.isPending
                  ? '推荐中...'
                  : quoteMutation.isPending
                    ? '报价中...'
                    : mode === 'manual'
                      ? '获取报价'
                      : '智能推荐'}
              </button>
            </div>
          </div>

          {/* Mode cards */}
          <div className="mode-cards">
            {MODE_OPTIONS.map((opt) => {
              const Icon = opt.icon
              const active = mode === opt.value
              return (
                <label key={opt.value} className={`mode-card ${active ? 'active' : ''}`}>
                  <input
                    type="radio"
                    value={opt.value}
                    {...register('mode')}
                  />
                  <div className="mode-card-icon" style={{ color: active ? opt.color : undefined }}>
                    <Icon size={20} />
                  </div>
                  <div className="mode-card-text">
                    <strong>{opt.label}</strong>
                    <small>{opt.desc}</small>
                  </div>
                  {active && <div className="mode-card-indicator" style={{ background: opt.color }} />}
                </label>
              )
            })}
          </div>

          {/* Advanced settings toggle */}
          <button
            type="button"
            className="advanced-toggle"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <Settings2 size={15} />
            高级设置
            <ChevronDown size={15} className={`advanced-chevron ${showAdvanced ? 'open' : ''}`} />
          </button>

          {showAdvanced && (
            <div className="advanced-panel">
              <div className="advanced-grid">
                {mode !== 'manual' && (
                  <>
                    <label className="field">
                      <span><ShieldCheck size={13} /> 质量要求</span>
                      <select {...register('qualityRequirement')}>
                        <option value="minimum">最低（简单分类/抽取）</option>
                        <option value="standard">标准（日常任务）</option>
                        <option value="high">较高（重要内容）</option>
                        <option value="critical">关键（代码/分析）</option>
                      </select>
                    </label>
                    <label className="field">
                      <span><Tag size={13} /> 任务类型</span>
                      <select {...register('taskType')}>
                        <option value="auto">自动检测</option>
                        <option value="classification">分类</option>
                        <option value="extraction">信息抽取</option>
                        <option value="summarization">摘要</option>
                        <option value="generation">内容生成</option>
                        <option value="analysis">分析推理</option>
                        <option value="code">代码</option>
                        <option value="translation">翻译</option>
                      </select>
                    </label>
                  </>
                )}

                {mode === 'manual' && (
                  <>
                    <label className="field">
                      <span><Sparkles size={13} /> 模型档位</span>
                      <select {...register('tier')} disabled={useExactModel}>
                        <option value="economy">经济档</option>
                        <option value="balanced">标准档</option>
                        <option value="quality">高质量档</option>
                      </select>
                    </label>
                    <label className="check-row advanced-check">
                      <input type="checkbox" {...register('useExactModel')} />
                      <span>自选具体模型</span>
                    </label>
                    {useExactModel && (
                      <label className="field" style={{ gridColumn: '1 / -1' }}>
                        <span>选择模型</span>
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
                  </>
                )}

                <label className="field">
                  <span><Clock3 size={13} /> 最大输出 Token</span>
                  <input type="number" min={16} max={4096} step={16} {...register('maxOutputTokens', { valueAsNumber: true })} />
                </label>
                <label className="check-row advanced-check">
                  <input type="checkbox" {...register('flexible')} />
                  <span>截止时间前弹性执行（更省碳）</span>
                </label>
                {flexible && (
                  <label className="field">
                    <span>最晚完成时间</span>
                    <input type="datetime-local" {...register('deadline', { required: true })} />
                  </label>
                )}
              </div>

              <details className="advanced-system-prompt">
                <summary>系统提示词（可选）</summary>
                <textarea {...register('systemPrompt', { maxLength: 4096 })} rows={2} placeholder="设置 AI 的角色或行为约束..." />
              </details>
            </div>
          )}
        </form>

        <div className="hero-truth">
          <span>模型输出与 Token</span><ProvenanceBadge value="measured" />
          <span>推荐与碳信号</span><ProvenanceBadge value="simulated" />
        </div>
      </section>

      {models.isError && <ErrorState message="模型目录暂时不可用。" />}
      {quoteError && <ErrorState message={quoteError} />}

      {/* Results flow */}
      {showRecommendation && recommendation?.task_understanding && (
        <section className="task-understanding-card">
          <div className="tu-header">
            <Lightbulb aria-hidden="true" size={18} />
            <span>系统理解你的任务</span>
            <span className={`tu-confidence tu-conf-${recommendation.task_understanding.confidence_label === '高' ? 'high' : recommendation.task_understanding.confidence_label === '中' ? 'medium' : 'low'}`}>
              置信度：{recommendation.task_understanding.confidence_label}
            </span>
          </div>
          <p className="tu-reasoning">{recommendation.task_understanding.reasoning}</p>
          <div className="tu-tags">
            <span className="tu-tag"><Tag size={12} /> {recommendation.task_understanding.task_type_label}</span>
            <span className="tu-tag">{recommendation.task_understanding.complexity_label}复杂度</span>
            <span className="tu-tag">
              约 {recommendation.task_understanding.estimated_output_tokens} 输出tokens
            </span>
            {recommendation.task_understanding.estimated_item_count > 1 && (
              <span className="tu-tag">批量 ~{recommendation.task_understanding.estimated_item_count} 条</span>
            )}
            {recommendation.task_understanding.requires_json && (
              <span className="tu-tag">结构化输出</span>
            )}
          </div>
          <p className="tu-hint">
            如果理解有误，可展开"高级设置"调整任务类型或质量要求后重新推荐。
          </p>
        </section>
      )}

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

      {/* Carbon signal footer hint */}
      {greenHint && (
        <Link to="/carbon" className="carbon-footer-hint">
          <Leaf size={15} />
          <span>
            当前最绿色时段 <strong>{greenHint.best.date.slice(5)} {String(greenHint.best.hour).padStart(2, '0')}:00</strong>
            （{greenHint.best.carbon_g_per_kwh} g/kWh），开启弹性执行可减少 <strong>{greenHint.saving}%</strong> 碳排放
          </span>
          <ArrowRight size={14} />
          <span className="carbon-footer-link">查看碳信号地图</span>
        </Link>
      )}
    </main>
  )
}
