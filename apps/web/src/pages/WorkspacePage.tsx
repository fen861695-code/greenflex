import { useMutation, useQuery } from '@tanstack/react-query'
import { Brain, Clock3, Gauge, ShieldCheck, Sparkles, Zap } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import {
  api,
  apiMessage,
  type ModelTier,
  type OutputLength,
  type QuoteOption,
  type QualityRequirement,
  type SolutionOption,
  type SolutionResponse,
  type TaskType,
} from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { QuoteOptions } from '../components/QuoteOptions'

type WorkspaceForm = {
  prompt: string
  systemPrompt: string
  outputLength: OutputLength
  qualityRequirement: QualityRequirement
  taskType: TaskType
  flexible: boolean
  deadline: string
  // Manual mode fields
  useManual: boolean
  tier: ModelTier
  modelId: string
  useExactModel: boolean
  maxOutputTokens: number
}

function defaultDeadline(): string {
  const date = new Date(Date.now() + 4 * 60 * 60 * 1_000)
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function estimateTokens(text: string): number {
  return Math.max(1, Math.ceil(text.length / 3))
}

const TASK_TYPE_LABELS: Record<TaskType, string> = {
  auto: '自动检测',
  classification: '分类/情感',
  extraction: '信息抽取',
  summarization: '摘要总结',
  analysis: '分析推理',
  generation: '内容生成',
  code: '代码',
}

const OUTPUT_LENGTH_LABELS: Record<OutputLength, string> = {
  short: '简短',
  medium: '中等',
  long: '详细',
}

const OUTPUT_LENGTH_HINTS: Record<OutputLength, string> = {
  short: '分类、标签、简短回答',
  medium: '摘要、常规分析、翻译',
  long: '长文写作、详细分析、代码生成',
}

const COMPLEXITY_LABELS: Record<string, string> = {
  low: '简单',
  medium: '中等',
  high: '复杂',
}

export function WorkspacePage() {
  const navigate = useNavigate()
  const [solution, setSolution] = useState<SolutionResponse | null>(null)
  const [solutionError, setSolutionError] = useState<string | null>(null)
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

  const { register, handleSubmit, watch, setValue } = useForm<WorkspaceForm>({
    defaultValues: {
      prompt: '',
      systemPrompt: '',
      outputLength: 'medium',
      qualityRequirement: 'standard',
      taskType: 'auto',
      flexible: false,
      deadline: defaultDeadline(),
      useManual: false,
      tier: 'balanced',
      modelId: 'qwen2.5-1.5b-q4',
      useExactModel: false,
      maxOutputTokens: 512,
    },
  })

  const useManual = watch('useManual')
  const flexible = watch('flexible')
  const promptValue = watch('prompt')
  const outputLength = watch('outputLength')

  // Unified solution mutation (smart mode)
  const solutionMutation = useMutation({
    mutationFn: async (values: WorkspaceForm) => {
      const body = {
        prompt: values.prompt,
        system_prompt: values.systemPrompt || null,
        output_length: values.outputLength,
        quality_requirement: values.qualityRequirement,
        task_type: values.taskType,
        mode: 'smart' as const,
        budget_rmb: null,
        deadline: values.flexible ? new Date(values.deadline).toISOString() : null,
        execution_mode: values.flexible ? 'flexible' : 'immediate',
      }
      const { data, error } = await (api.POST as any)('/api/v1/solutions', { body })
      if (error) throw new Error(apiMessage(error))
      return data as unknown as SolutionResponse
    },
    onSuccess: (sol) => {
      setSolution(sol)
      setSolutionError(null)
      setQuotes([])
    },
    onError: (error) => setSolutionError(apiMessage(error)),
  })

  // Manual quote mutation
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
      setSolution(null)
    },
    onError: (error) => setQuoteError(apiMessage(error)),
  })

  const orderMutation = useMutation({
    mutationFn: async (quoteId: string) => {
      const { data, error } = await api.POST('/api/v1/orders', {
        body: { quote_id: quoteId },
      })
      if (error) throw new Error(apiMessage(error))
      return data
    },
    onSuccess: (order) => navigate(`/orders/${order.id}`),
    onError: (error) => setSolutionError(apiMessage(error)),
  })

  const onSubmit = (values: WorkspaceForm) => {
    if (values.useManual) {
      quoteMutation.mutate(values)
    } else {
      solutionMutation.mutate(values)
    }
  }

  const handleSelectSolution = (option: SolutionOption) => {
    orderMutation.mutate(option.quote_id)
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
              placeholder="输入待处理文本，系统将自动判断任务类型和复杂度"
            />
            <small>
              {promptValue.length.toLocaleString()} / 8,192 · 约{' '}
              {estimateTokens(promptValue).toLocaleString()} tokens
            </small>
          </label>

          <details className="advanced-fields">
            <summary>系统提示词（可选）</summary>
            <label className="field">
              <span className="sr-only">系统提示词</span>
              <textarea {...register('systemPrompt', { maxLength: 4096 })} rows={3} />
            </label>
          </details>
        </section>

        <aside className="order-settings">
          {/* Output length - replaces manual token count */}
          <div className="settings-block">
            <div className="field-heading">
              <Gauge aria-hidden="true" />
              <span>输出长度</span>
            </div>
            <div className="segmented three">
              <label>
                <input type="radio" value="short" {...register('outputLength')} />
                <span>简短</span>
              </label>
              <label>
                <input type="radio" value="medium" {...register('outputLength')} />
                <span>中等</span>
              </label>
              <label>
                <input type="radio" value="long" {...register('outputLength')} />
                <span>详细</span>
              </label>
            </div>
            <p className="mode-hint">{OUTPUT_LENGTH_HINTS[outputLength]}</p>
          </div>

          {/* Quality requirement */}
          <div className="settings-block">
            <div className="field-heading">
              <ShieldCheck aria-hidden="true" />
              <span>质量要求</span>
            </div>
            <select {...register('qualityRequirement')}>
              <option value="minimum">最低（简单分类/抽取）</option>
              <option value="standard">标准（日常任务）</option>
              <option value="high">较高（重要内容）</option>
              <option value="critical">关键（代码/分析）</option>
            </select>

            <label className="field" style={{ marginTop: '0.5rem' }}>
              <span>任务类型</span>
              <select {...register('taskType')}>
                {Object.entries(TASK_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {/* Execution time */}
          <div className="settings-block">
            <div className="field-heading">
              <Clock3 aria-hidden="true" />
              <span>执行时间</span>
            </div>
            <label className="check-row">
              <input type="checkbox" {...register('flexible')} />
              <span>截止时间前弹性执行（更便宜）</span>
            </label>
            {flexible && (
              <label className="field">
                <span>最晚完成时间</span>
                <input type="datetime-local" {...register('deadline', { required: true })} />
              </label>
            )}
          </div>

          {/* Submit button */}
          <button
            className="button primary full"
            type="submit"
            disabled={solutionMutation.isPending || quoteMutation.isPending}
          >
            <Sparkles aria-hidden="true" />
            {solutionMutation.isPending
              ? '正在智能分析...'
              : quoteMutation.isPending
                ? '正在计算报价...'
                : useManual
                  ? '获取报价'
                  : '智能推荐并报价'}
          </button>

          {/* Manual mode toggle */}
          <label className="check-row" style={{ marginTop: '0.75rem' }}>
            <input type="checkbox" {...register('useManual')} />
            <span>手动选择模型（高级）</span>
          </label>

          {useManual && (
            <div className="settings-block" style={{ marginTop: '0.5rem' }}>
              <div className="field-heading">
                <Brain aria-hidden="true" />
                <span>模型选择</span>
              </div>
              <div className="segmented three">
                <label>
                  <input type="radio" value="economy" {...register('tier')} disabled={watch('useExactModel')} />
                  <span>经济</span>
                </label>
                <label>
                  <input type="radio" value="balanced" {...register('tier')} disabled={watch('useExactModel')} />
                  <span>标准</span>
                </label>
                <label>
                  <input type="radio" value="quality" {...register('tier')} disabled={watch('useExactModel')} />
                  <span>高质量</span>
                </label>
              </div>
              <label className="check-row">
                <input type="checkbox" {...register('useExactModel')} />
                <span>指定具体模型</span>
              </label>
              {watch('useExactModel') && (
                <label className="field">
                  <span>本地模型</span>
                  {models.isLoading ? (
                    <LoadingState label="检测模型" />
                  ) : (
                    <select {...register('modelId')}>
                      {models.data?.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.display_name}
                          {model.available ? '' : '（不可用）'}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              )}
              <label className="field compact">
                <span>最大输出 Token</span>
                <input
                  type="number"
                  min="16"
                  max="2048"
                  step="16"
                  {...register('maxOutputTokens', { valueAsNumber: true })}
                />
              </label>
            </div>
          )}

          <div className="truth-strip">
            <span>模型输出与 Token</span>
            <ProvenanceBadge value="measured" />
            <span>推荐与碳信号</span>
            <ProvenanceBadge value="simulated" />
          </div>
        </aside>
      </form>

      {models.isError && <ErrorState message="模型目录暂时不可用。" />}
      {solutionError && <ErrorState message={solutionError} />}
      {quoteError && <ErrorState message={quoteError} />}

      {/* Solution results - unified smart mode */}
      {solution && (
        <section className="solution-results">
          <div className="solution-summary">
            <h3>
              <Zap aria-hidden="true" />
              智能分析结果
            </h3>
            <div className="solution-meta">
              <span>
                任务类型：<strong>{TASK_TYPE_LABELS[solution.detected_task_type]}</strong>
                {solution.task_classification_confidence_bps && (
                  <em>（置信度 {(solution.task_classification_confidence_bps / 100).toFixed(0)}%）</em>
                )}
              </span>
              <span>
                复杂度：<strong>{COMPLEXITY_LABELS[solution.complexity_level] || solution.complexity_level}</strong>
              </span>
              <span>
                预估输入：<strong>{solution.estimated_input_tokens} tokens</strong>
              </span>
              <span>
                预估输出：<strong>{solution.estimated_output_tokens} tokens</strong>
              </span>
            </div>
          </div>

          <div className="solution-options">
            {solution.options.map((option) => (
              <article
                key={option.quote_id}
                className={`solution-card ${option.is_recommended ? 'recommended' : ''}`}
              >
                {option.is_recommended && (
                  <div className="solution-badge">最推荐</div>
                )}
                <header>
                  <h4>{option.model_name}</h4>
                  <span className="solution-tier">
                    {option.tier === 'economy' ? '经济型' : option.tier === 'balanced' ? '均衡型' : '高质量型'}
                  </span>
                </header>

                <div className="solution-price">
                  <span className="price-amount">¥{option.total_price_rmb}</span>
                  {option.discount_percent !== '0.00%' && (
                    <span className="price-discount">省 {option.discount_percent}</span>
                  )}
                </div>

                <dl className="solution-stats">
                  <div>
                    <dt>能耗</dt>
                    <dd>{option.facility_energy_wh_est} Wh</dd>
                  </div>
                  <div>
                    <dt>碳排放</dt>
                    <dd>{option.carbon_g_est} g</dd>
                  </div>
                  <div>
                    <dt>预计耗时</dt>
                    <dd>{option.estimated_execution_seconds}s</dd>
                  </div>
                  <div>
                    <dt>绿电比例</dt>
                    <dd>{option.renewable_share_percent}</dd>
                  </div>
                </dl>

                <p className="solution-reason">{option.reason_summary}</p>

                <div className="solution-confidence">
                  <span>推荐置信度：{option.confidence_label}</span>
                  <span>质量风险：{option.quality_risk === 'low' ? '低' : option.quality_risk === 'medium' ? '中' : option.quality_risk === 'high' ? '高' : '极高'}</span>
                </div>

                <button
                  className="button primary full"
                  type="button"
                  onClick={() => handleSelectSolution(option)}
                  disabled={orderMutation.isPending}
                >
                  {orderMutation.isPending && orderMutation.variables === option.quote_id
                    ? '正在下单...'
                    : '选择此方案'}
                </button>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* Manual quote results */}
      <QuoteOptions
        options={quotes}
        onSelect={(quote) => orderMutation.mutate(quote.quote_id)}
        pendingQuoteId={orderMutation.isPending ? (orderMutation.variables as string) : undefined}
      />
    </main>
  )
}
