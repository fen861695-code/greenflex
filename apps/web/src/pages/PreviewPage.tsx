import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, Play, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'

import { api, apiMessage, type PreviewResponse } from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { formatNumber } from '../utils/format'

type PreviewForm = { prompt: string; systemPrompt: string; maxOutputTokens: number }
type PreviewRun = PreviewResponse & { modelName: string }

export function PreviewPage() {
  const [selected, setSelected] = useState<string[]>([])
  const [runError, setRunError] = useState<string | null>(null)
  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/models')
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })
  useEffect(() => {
    if (selected.length === 0 && models.data) {
      setSelected(models.data.filter((model) => model.enabled && !model.is_task_classifier).slice(0, 3).map((model) => model.id))
    }
  }, [models.data, selected.length])
  const { register, handleSubmit, watch } = useForm<PreviewForm>({
    defaultValues: { prompt: '', systemPrompt: '', maxOutputTokens: 128 },
  })
  const previewMutation = useMutation({
    mutationFn: async (values: PreviewForm) => {
      const results: PreviewRun[] = []
      for (const modelId of selected) {
        const model = models.data?.find((item) => item.id === modelId)
        if (!model) continue
        const { data, error } = await api.POST('/api/v1/previews', {
          body: {
            model_id: modelId,
            prompt: values.prompt,
            system_prompt: values.systemPrompt || null,
            max_output_tokens: values.maxOutputTokens,
          },
        })
        if (error) throw new Error(apiMessage(error))
        results.push({ ...data, modelName: model.display_name })
      }
      return results
    },
    onMutate: () => setRunError(null),
    onError: (error) => setRunError(apiMessage(error)),
  })
  const toggleModel = (id: string) => {
    setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
  }

  return (
    <main className="page">
      <PageHeader eyebrow="模型对比" title="模型试跑对比" actions={<ProvenanceBadge value="simulated" detail="模拟推理模式，配置云 API Key 后可真实调用" />} />
      <form className="preview-layout" onSubmit={handleSubmit((values) => previewMutation.mutate(values))}>
        <section className="preview-input">
          <label className="field"><span>试跑文本</span><textarea rows={10} {...register('prompt', { required: true, maxLength: 8192 })} placeholder="输入同一段文本，按顺序对比所选模型" /><small>{watch('prompt').length.toLocaleString()} / 8,192</small></label>
          <details className="advanced-fields"><summary>系统提示词</summary><textarea rows={3} {...register('systemPrompt', { maxLength: 4096 })} /></details>
        </section>
        <aside className="preview-models">
          <div className="section-heading compact"><div><p className="eyebrow">串行执行</p><h2>选择模型</h2></div><Zap aria-hidden="true" /></div>
          {models.isLoading && <LoadingState label="加载模型目录" />}
          {models.data?.filter((m) => m.enabled && !m.is_task_classifier).map((model) => (
            <label className="model-choice" key={model.id}>
              <input type="checkbox" checked={selected.includes(model.id)} onChange={() => toggleModel(model.id)} />
              <span className="custom-check"><Check aria-hidden="true" /></span>
              <span><strong>{model.display_name}</strong><small>{model.parameter_b} · {model.availability_detail}{model.recommended_batch_size && model.recommended_batch_size > 1 ? ` · 推荐批量 ${String(model.recommended_batch_size)}` : ''}</small></span>
            </label>
          ))}
          <label className="field compact"><span>最大输出 Token</span><input type="number" min="16" max="512" step="16" {...register('maxOutputTokens', { valueAsNumber: true })} /></label>
          <button className="button primary full" type="submit" disabled={selected.length === 0 || previewMutation.isPending}><Play aria-hidden="true" />{previewMutation.isPending ? '正在顺序试跑' : `运行 ${String(selected.length)} 个模型`}</button>
        </aside>
      </form>
      {models.isError && <ErrorState message="无法读取模型目录。" />}
      {runError && <ErrorState message={runError} />}
      {previewMutation.data && previewMutation.data.length > 0 && (
        <section className="results-section">
          <div className="section-heading"><div><p className="eyebrow">本次结果</p><h2>实测对比</h2></div><ProvenanceBadge value="measured" /></div>
          <div className="preview-results">
            {previewMutation.data.map((result) => (
              <article className="result-card" key={result.model_id}>
                <header><strong>{result.modelName}</strong><ProvenanceBadge value={result.telemetry_provenance} /></header>
                <div className="result-output">{result.output}</div>
                <dl className="result-metrics">
                  <div><dt>输入 Token</dt><dd>{result.prompt_tokens}</dd></div>
                  <div><dt>输出 Token</dt><dd>{result.output_tokens}</dd></div>
                  <div><dt>延迟</dt><dd>{formatNumber(result.latency_ms, 1)} ms</dd></div>
                  <div><dt>GPU 总能耗</dt><dd>{formatNumber(result.gross_gpu_energy_wh, 6)} Wh</dd></div>
                  {result.joules_per_output_token && (
                    <div><dt>能效 J/tok</dt><dd>{result.joules_per_output_token} J</dd></div>
                  )}
                </dl>
              </article>
            ))}
          </div>
        </section>
      )}
    </main>
  )
}
