import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Brain, Cpu, Database, Play, RefreshCw, Shield, Zap } from 'lucide-react'
import { api, apiMessage, type RLDecision, type RLMode, type RLStatus, type RLTrainResult } from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'

const modeLabels: Record<RLMode, string> = {
  disabled: '已禁用',
  shadow: '影子模式',
  advisory: '建议模式',
  autonomous: '自主模式',
}

const modeDescriptions: Record<RLMode, string> = {
  disabled: 'RL路由器不参与任何路由决策',
  shadow: '记录决策但不影响实际路由，用于收集训练数据',
  advisory: '给出路由建议，由用户确认后执行',
  autonomous: '自动执行RL路由决策（需要已训练策略）',
}

export function RLRouterPage() {
  const queryClient = useQueryClient()

  const status = useQuery<RLStatus>({
    queryKey: ['rl-status'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/rl/status')
      if (error) throw new Error(apiMessage(error))
      return data as RLStatus
    },
    refetchInterval: 5000,
  })

  const decisions = useQuery<RLDecision[]>({
    queryKey: ['rl-decisions'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/rl/decisions', { params: { query: { limit: 20 } } })
      if (error) throw new Error(apiMessage(error))
      return data as RLDecision[]
    },
    refetchInterval: 5000,
  })

  const setModeMutation = useMutation({
    mutationFn: async (mode: RLMode) => {
      const { data, error } = await api.POST('/api/v1/rl/mode', { params: { query: { mode } } })
      if (error) throw new Error(apiMessage(error))
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rl-status'] })
    },
  })

  const trainMutation = useMutation<RLTrainResult>({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/rl/train')
      if (error) throw new Error(apiMessage(error))
      return data as RLTrainResult
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rl-status'] })
    },
  })

  if (status.isLoading) return <main className="page"><LoadingState label="加载 RL 路由器状态" /></main>
  if (status.isError || !status.data) return <main className="page"><ErrorState message={apiMessage(status.error)} /></main>

  const rl = status.data

  return (
    <main className="page rl-page">
      <PageHeader
        eyebrow="强化学习路由"
        title="RL 路由器控制台"
        actions={<ProvenanceBadge value="simulated" detail="RL策略为本地训练仿真" />}
      />

      {!rl.enabled ? (
        <div className="notice warning">
          <Shield aria-hidden="true" />
          <span>RL 路由器当前未启用。{rl.message ?? '请检查后端配置。'}</span>
        </div>
      ) : (
        <>
          {/* 状态概览 */}
          <div className="rl-summary-band">
            <div className="rl-stat">
              <div className="rl-stat-icon"><Brain aria-hidden="true" /></div>
              <div>
                <span>运行模式</span>
                <strong>{rl.mode ? modeLabels[rl.mode] : '—'}</strong>
                <small>{rl.mode ? modeDescriptions[rl.mode] : ''}</small>
              </div>
            </div>
            <div className="rl-stat">
              <div className="rl-stat-icon"><Activity aria-hidden="true" /></div>
              <div>
                <span>会话状态</span>
                <strong>{rl.session_state ?? '—'}</strong>
                <small>策略版本：{rl.policy_version ?? '未初始化'}</small>
              </div>
            </div>
            <div className="rl-stat">
              <div className="rl-stat-icon"><Database aria-hidden="true" /></div>
              <div>
                <span>经验回放池</span>
                <strong>{rl.buffer_size ?? 0} / {rl.total_transitions ?? 0}</strong>
                <small>已收集转换样本</small>
              </div>
            </div>
            <div className="rl-stat">
              <div className="rl-stat-icon"><Zap aria-hidden="true" /></div>
              <div>
                <span>训练更新</span>
                <strong>{rl.total_updates ?? 0} 次</strong>
                <small>决策日志：{rl.decision_log_size ?? 0} 条</small>
              </div>
            </div>
          </div>

          {/* 模式切换 */}
          <section className="rl-section">
            <div className="section-heading">
              <h2>路由模式</h2>
              <small>选择 RL 路由器的工作模式</small>
            </div>
            <div className="rl-mode-grid">
              {(['disabled', 'shadow', 'advisory', 'autonomous'] as RLMode[]).map((mode) => (
                <button
                  key={mode}
                  className={`rl-mode-card ${rl.mode === mode ? 'active' : ''}`}
                  onClick={() => setModeMutation.mutate(mode)}
                  disabled={setModeMutation.isPending}
                >
                  <strong>{modeLabels[mode]}</strong>
                  <span>{modeDescriptions[mode]}</span>
                  {rl.mode === mode && <span className="rl-mode-active">当前模式</span>}
                </button>
              ))}
            </div>
            {setModeMutation.isError && (
              <div className="notice danger"><span>{apiMessage(setModeMutation.error)}</span></div>
            )}
          </section>

          {/* 训练控制 */}
          <section className="rl-section">
            <div className="section-heading">
              <h2>策略训练</h2>
              <button
                className="button secondary"
                onClick={() => trainMutation.mutate()}
                disabled={trainMutation.isPending || (rl.buffer_size ?? 0) < 10}
              >
                <Play aria-hidden="true" />
                {trainMutation.isPending ? '训练中...' : '触发训练步骤'}
              </button>
            </div>
            <div className="rl-training-info">
              <div className="rl-progress">
                <div className="rl-progress-bar">
                  <div
                    className="rl-progress-fill"
                    style={{ width: `${String(Math.min(100, ((rl.buffer_size ?? 0) / 10) * 100))}%` }}
                  />
                </div>
                <span>已收集 {rl.buffer_size ?? 0} / 10 样本（最少10个开始训练）</span>
              </div>
              {trainMutation.data && (
                <div className="rl-train-result">
                  <span>训练结果：{trainMutation.data.status}</span>
                  {trainMutation.data.loss !== undefined && <span>Loss：{trainMutation.data.loss.toFixed(4)}</span>}
                  {trainMutation.data.reward_mean !== undefined && <span>平均奖励：{trainMutation.data.reward_mean.toFixed(3)}</span>}
                </div>
              )}
              {trainMutation.isError && (
                <div className="notice danger"><span>{apiMessage(trainMutation.error)}</span></div>
              )}
            </div>
          </section>

          {/* 性能指标 */}
          <section className="rl-section">
            <div className="section-heading"><h2>性能指标</h2></div>
            <div className="rl-metrics-grid">
              <div className="rl-metric-card">
                <Cpu aria-hidden="true" />
                <span>与基线一致率</span>
                <strong>{((rl.recent_agreement_rate ?? 0) * 100).toFixed(1)}%</strong>
              </div>
              <div className="rl-metric-card">
                <Activity aria-hidden="true" />
                <span>探索温度</span>
                <strong>{rl.temperature?.toFixed(2) ?? '—'}</strong>
              </div>
              <div className="rl-metric-card">
                <Brain aria-hidden="true" />
                <span>策略已初始化</span>
                <strong>{rl.policy_initialized ? '是' : '否'}</strong>
              </div>
              <div className="rl-metric-card">
                <RefreshCw aria-hidden="true" />
                <span>候选模型数</span>
                <strong>{rl.candidate_models?.length ?? 0}</strong>
              </div>
            </div>
          </section>

          {/* 决策日志 */}
          <section className="rl-section">
            <div className="section-heading">
              <h2>最近路由决策</h2>
              <small>自动刷新（5秒）</small>
            </div>
            {decisions.isLoading ? (
              <LoadingState label="加载决策日志" />
            ) : decisions.data && decisions.data.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>请求哈希</th>
                      <th>RL推荐</th>
                      <th>基线选择</th>
                      <th>奖励</th>
                      <th>模式</th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.data.map((d, i) => (
                      <tr key={i}>
                        <td>{d.timestamp}</td>
                        <td><code className="hash-value">{d.request_hash.slice(0, 12)}...</code></td>
                        <td>{d.recommended_model}</td>
                        <td>{d.baseline_model}</td>
                        <td>{d.reward === null ? '—' : d.reward.toFixed(4)}</td>
                        <td><span className="badge neutral">{d.mode}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <Activity aria-hidden="true" />
                <span>暂无路由决策记录</span>
                <small>在影子或建议模式下处理订单后会显示决策日志</small>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  )
}
