import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Bot,
  Leaf,
  MessageSquare,
  Plus,
  Send,
  Sparkles,
  Trash2,
  User,
  Wrench,
  Zap,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { api, apiMessage, type ChatMessage, type ChatResponse } from '../api/client'
import { ErrorState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'
import { ProvenanceBadge } from '../components/ProvenanceBadge'
import { formatNumber } from '../utils/format'

interface ConversationMessage extends ChatMessage {
  id: string
  metrics?: {
    prompt_tokens: number
    completion_tokens: number
    duration_ms: number
    price_micro_rmb: number
    energy_micro_wh: number
    carbon_micro_g: number
    source: string
  }
  toolsUsed?: string[]
  agentMode?: string
}

interface ConciergeResponse {
  session_id: string
  reply: string
  agent_mode: string
  tools_used: string[]
}

const CONCIERGE_SESSION_KEY = 'greenflex_concierge_session'

function microRmbToYuan(micro: number): string {
  return (micro / 1_000_000).toFixed(6)
}

function microWhToWh(micro: number): string {
  return (micro / 1_000_000).toFixed(4)
}

function microGToG(micro: number): string {
  return (micro / 1_000_000).toFixed(4)
}

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    hybrid: '混合路由',
    'cloud-api': '云端 API',
    simulated: '模拟推理',
    'nvidia-smi': '本地 GPU',
    nvml: '本地 GPU (NVML)',
  }
  return labels[source] ?? source
}

const TOOL_LABELS: Record<string, string> = {
  analyze_task: '任务分析',
  chat_with_model: '模型对话',
  list_models: '模型列表',
  get_carbon_status: '碳信号',
  preview_model: '模型试跑',
  get_order_status: '订单查询',
}

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name
}

export function ChatPage() {
  const [mode, setMode] = useState<'concierge' | 'direct'>('concierge')
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [input, setInput] = useState('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [showSystem, setShowSystem] = useState(false)
  const [conciergeSession] = useState(
    () => sessionStorage.getItem(CONCIERGE_SESSION_KEY) ?? crypto.randomUUID(),
  )
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    sessionStorage.setItem(CONCIERGE_SESSION_KEY, conciergeSession)
  }, [conciergeSession])

  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/models')
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })

  const conciergeHealth = useQuery({
    queryKey: ['concierge-health'],
    queryFn: async () => {
      const resp = await fetch('/api/v1/concierge/health')
      if (!resp.ok) throw new Error('health check failed')
      return (await resp.json()) as {
        status: string
        llm_available: boolean
        llm_provider: string
        llm_model: string
      }
    },
    refetchInterval: 30_000,
  })

  const enabledModels =
    models.data?.filter((m) => m.enabled && !m.is_task_classifier) ?? []
  const effectiveModel =
    selectedModel || enabledModels[0]?.id || models.data?.[0]?.id || ''

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = `${String(Math.min(ta.scrollHeight, 200))}px`
    }
  }, [input])

  // Concierge (agent) chat
  const conciergeMutation = useMutation({
    mutationFn: async (message: string) => {
      const resp = await fetch('/api/v1/concierge/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: conciergeSession, message }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || err.message || '管家请求失败')
      }
      return (await resp.json()) as ConciergeResponse
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.reply,
          toolsUsed: data.tools_used,
          agentMode: data.agent_mode,
        },
      ])
    },
  })

  // Direct model chat
  const chatMutation = useMutation({
    mutationFn: async (msgHistory: ConversationMessage[]) => {
      const apiMessages: ChatMessage[] = []
      if (systemPrompt.trim()) {
        apiMessages.push({ role: 'system', content: systemPrompt.trim() })
      }
      for (const m of msgHistory) {
        apiMessages.push({ role: m.role, content: m.content })
      }
      const { data, error } = await api.POST('/api/v1/chat', {
        body: {
          model_id: effectiveModel,
          messages: apiMessages,
          max_output_tokens: 2048,
          temperature: 0.7,
        },
      })
      if (error) throw new Error(apiMessage(error))
      return data as ChatResponse
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.reply,
          metrics: {
            prompt_tokens: data.prompt_tokens,
            completion_tokens: data.completion_tokens,
            duration_ms: data.duration_ms,
            price_micro_rmb: data.estimated_price_micro_rmb,
            energy_micro_wh: data.estimated_energy_micro_wh,
            carbon_micro_g: data.estimated_carbon_micro_g,
            source: data.inference_source,
          },
        },
      ])
    },
  })

  const isPending =
    mode === 'concierge' ? conciergeMutation.isPending : chatMutation.isPending

  const handleSend = () => {
    const text = input.trim()
    if (!text || isPending) return
    if (mode === 'direct' && !effectiveModel) return

    const userMsg: ConversationMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')

    if (mode === 'concierge') {
      conciergeMutation.mutate(text)
    } else {
      chatMutation.mutate([...messages, userMsg])
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewConversation = () => {
    setMessages([])
    setInput('')
    if (mode === 'concierge') {
      fetch('/api/v1/concierge/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: conciergeSession }),
      }).catch(() => {})
    }
  }

  const selectedModelData = models.data?.find((m) => m.id === effectiveModel)
  const isCloudModel = selectedModelData?.id.startsWith('cloud-')
  const llmAvailable = conciergeHealth.data?.llm_available ?? false

  const conciergeSuggestions = [
    '帮我分析一批评论的情感倾向，大概500条',
    '总结这篇文章的要点',
    '现在哪个地区的电网最绿？',
    '有哪些便宜又快的模型？',
    '帮我写一个 Python 排序函数',
    '翻译这段话成英文',
  ]

  const directSuggestions = [
    '解释一下什么是绿色算力？',
    '如何降低大模型推理的碳排放？',
    '帮我写一个 Python 快速排序',
    '总结一下分时电价的工作原理',
  ]

  return (
    <main className="page chat-page">
      <PageHeader
        eyebrow="AI 对话"
        title={mode === 'concierge' ? '绿色推理管家' : '智能问答'}
        actions={
          <div className="chat-header-actions">
            {mode === 'concierge' ? (
              <ProvenanceBadge
                value={llmAvailable ? 'measured' : 'simulated'}
                detail={
                  llmAvailable
                    ? `已连接 ${conciergeHealth.data?.llm_provider} (${conciergeHealth.data?.llm_model})`
                    : '规则模式 — 配置云 API Key 后启用智能对话'
                }
              />
            ) : (
              <ProvenanceBadge
                value={
                  chatMutation.data?.inference_source === 'cloud-api'
                    ? 'measured'
                    : 'simulated'
                }
                detail={
                  isCloudModel
                    ? '云端模型需配置 API Key'
                    : '当前为模拟推理，配置云 Key 后可真实调用'
                }
              />
            )}
            <button
              className="ghost-button"
              onClick={handleNewConversation}
              disabled={messages.length === 0}
              title="新对话"
            >
              <Plus aria-hidden="true" />
              <span>新对话</span>
            </button>
          </div>
        }
      />

      {/* Mode toggle */}
      <div className="chat-mode-toggle">
        <button
          className={`mode-tab ${mode === 'concierge' ? 'active' : ''}`}
          onClick={() => setMode('concierge')}
        >
          <Sparkles aria-hidden="true" size={16} />
          <span>智能管家</span>
        </button>
        <button
          className={`mode-tab ${mode === 'direct' ? 'active' : ''}`}
          onClick={() => setMode('direct')}
        >
          <MessageSquare aria-hidden="true" size={16} />
          <span>直接对话</span>
        </button>
      </div>

      {/* Direct mode: model selector */}
      {mode === 'direct' && (
        <div className="chat-toolbar">
          <label className="chat-model-select">
            <MessageSquare aria-hidden="true" size={16} />
            <select
              value={effectiveModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={models.isLoading}
            >
              {models.isLoading && <option>加载模型中...</option>}
              {models.data
                ?.filter((m) => m.enabled && !m.is_task_classifier)
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name} ({m.tier})
                  </option>
                ))}
            </select>
          </label>
          <button
            className="ghost-button"
            onClick={() => setShowSystem(!showSystem)}
            title="系统提示词"
          >
            <Sparkles aria-hidden="true" size={16} />
            <span>系统提示词</span>
          </button>
          {selectedModelData && (
            <span className="chat-model-info">
              {isCloudModel ? '云端' : '本地'} · {selectedModelData.tier} ·{' '}
              {formatNumber(selectedModelData.estimated_tokens_per_second)} tok/s
            </span>
          )}
        </div>
      )}

      {mode === 'direct' && showSystem && (
        <div className="chat-system-prompt">
          <textarea
            placeholder="设置系统提示词，例如：你是一个专业的绿色计算顾问..."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={2}
          />
        </div>
      )}

      {/* Concierge mode: info banner */}
      {mode === 'concierge' && !llmAvailable && messages.length === 0 && (
        <div className="concierge-banner">
          <Sparkles aria-hidden="true" size={18} />
          <div>
            <strong>智能管家当前为规则模式</strong>
            <p>
              可以帮你分析任务、推荐模型、查询碳信号。在
              <strong> 设置 </strong>
              页面配置 DeepSeek 等云 API Key 后，即可启用自然语言对话和任务执行。
            </p>
          </div>
        </div>
      )}

      {/* Messages area */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            {mode === 'concierge' ? (
              <>
                <div className="concierge-avatar-lg">
                  <Sparkles aria-hidden="true" size={40} />
                </div>
                <h3>你好，我是绿色推理管家</h3>
                <p>
                  描述你的任务，我来推荐最合适的模型，对比价格、能耗和碳排。
                </p>
                <div className="chat-suggestions">
                  {conciergeSuggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      className="chat-suggestion"
                      onClick={() => setInput(suggestion)}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <Bot aria-hidden="true" size={48} />
                <h3>开始对话</h3>
                <p>选择一个模型，输入你的问题。支持多轮对话上下文。</p>
                <div className="chat-suggestions">
                  {directSuggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      className="chat-suggestion"
                      onClick={() => setInput(suggestion)}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`chat-msg ${msg.role}`}>
              <div className="chat-msg-avatar">
                {msg.role === 'user' ? (
                  <User aria-hidden="true" size={18} />
                ) : mode === 'concierge' ? (
                  <Sparkles aria-hidden="true" size={18} />
                ) : (
                  <Bot aria-hidden="true" size={18} />
                )}
              </div>
              <div className="chat-msg-body">
                <div className="chat-msg-content">{msg.content}</div>
                {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                  <div className="chat-msg-tools">
                    <Wrench aria-hidden="true" size={12} />
                    {msg.toolsUsed.map((t) => (
                      <span key={t} className="tool-tag">
                        {toolLabel(t)}
                      </span>
                    ))}
                    {msg.agentMode === 'rule' && (
                      <span className="mode-tag rule">规则模式</span>
                    )}
                  </div>
                )}
                {msg.metrics && (
                  <div className="chat-msg-metrics">
                    <span title="推理来源">
                      <Zap aria-hidden="true" size={12} />
                      {sourceLabel(msg.metrics.source)}
                    </span>
                    <span title="Token 数">
                      {formatNumber(
                        msg.metrics.prompt_tokens + msg.metrics.completion_tokens,
                      )}{' '}
                      tokens
                    </span>
                    <span title="耗时">{msg.metrics.duration_ms} ms</span>
                    <span title="预估费用">
                      ¥{microRmbToYuan(msg.metrics.price_micro_rmb)}
                    </span>
                    <span title="GPU 能耗">
                      {microWhToWh(msg.metrics.energy_micro_wh)} Wh
                    </span>
                    <span title="碳排放" className="carbon">
                      <Leaf aria-hidden="true" size={12} />
                      {microGToG(msg.metrics.carbon_micro_g)} g
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        {isPending && (
          <div className="chat-msg assistant">
            <div className="chat-msg-avatar">
              {mode === 'concierge' ? (
                <Sparkles aria-hidden="true" size={18} />
              ) : (
                <Bot aria-hidden="true" size={18} />
              )}
            </div>
            <div className="chat-msg-body">
              <div className="chat-typing">
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        )}
        {(conciergeMutation.isError || chatMutation.isError) && (
          <div className="chat-error">
            <ErrorState
              message={apiMessage(
                mode === 'concierge'
                  ? conciergeMutation.error
                  : chatMutation.error,
              )}
            />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="chat-input-area">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            mode === 'concierge'
              ? '描述你的任务，例如：帮我分类500条客户评论...'
              : '输入消息... (Enter 发送，Shift+Enter 换行)'
          }
          rows={1}
          disabled={isPending}
        />
        <button
          className="send-button"
          onClick={handleSend}
          disabled={!input.trim() || isPending || (mode === 'direct' && !effectiveModel)}
          title="发送"
        >
          <Send aria-hidden="true" size={18} />
        </button>
      </div>

      {messages.length > 0 && (
        <div className="chat-footer">
          <button className="text-button" onClick={handleNewConversation}>
            <Trash2 aria-hidden="true" size={14} />
            清空对话
          </button>
        </div>
      )}
    </main>
  )
}
