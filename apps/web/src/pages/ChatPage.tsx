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
}

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
    'hybrid': '混合路由',
    'cloud-api': '云端 API',
    simulated: '模拟推理',
    'nvidia-smi': '本地 GPU',
    nvml: '本地 GPU (NVML)',
  }
  return labels[source] ?? source
}

export function ChatPage() {
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [input, setInput] = useState('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [showSystem, setShowSystem] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const models = useQuery({
    queryKey: ['models'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/models')
      if (error) throw new Error(apiMessage(error))
      return data
    },
  })

  // Derive the effective selected model: user choice or first enabled non-classifier
  const enabledModels = models.data?.filter(
    (m) => m.enabled && !m.is_task_classifier,
  ) ?? []
  const effectiveModel = selectedModel || enabledModels[0]?.id || models.data?.[0]?.id || ''

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = `${String(Math.min(ta.scrollHeight, 200))}px`
    }
  }, [input])

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

  const handleSend = () => {
    const text = input.trim()
    if (!text || chatMutation.isPending || !effectiveModel) return

    const userMsg: ConversationMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    }
    const newHistory = [...messages, userMsg]
    setMessages(newHistory)
    setInput('')
    chatMutation.mutate(newHistory)
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
  }

  const selectedModelData = models.data?.find((m) => m.id === effectiveModel)
  const isCloudModel = selectedModelData?.id.startsWith('cloud-')

  return (
    <main className="page chat-page">
      <PageHeader
        eyebrow="AI 对话"
        title="智能问答"
        actions={
          <div className="chat-header-actions">
            <ProvenanceBadge
              value={chatMutation.data?.inference_source === 'cloud-api' ? 'measured' : 'simulated'}
              detail={
                isCloudModel
                  ? '云端模型需配置 API Key'
                  : '当前为模拟推理，配置云 Key 后可真实调用'
              }
            />
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

      {/* Model selector bar */}
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

      {showSystem && (
        <div className="chat-system-prompt">
          <textarea
            placeholder="设置系统提示词，例如：你是一个专业的绿色计算顾问..."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={2}
          />
        </div>
      )}

      {/* Messages area */}
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <Bot aria-hidden="true" size={48} />
            <h3>开始对话</h3>
            <p>选择一个模型，输入你的问题。支持多轮对话上下文。</p>
            <div className="chat-suggestions">
              {[
                '解释一下什么是绿色算力？',
                '如何降低大模型推理的碳排放？',
                '帮我写一个 Python 快速排序',
                '总结一下分时电价的工作原理',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  className="chat-suggestion"
                  onClick={() => setInput(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`chat-msg ${msg.role}`}>
              <div className="chat-msg-avatar">
                {msg.role === 'user' ? <User aria-hidden="true" size={18} /> : <Bot aria-hidden="true" size={18} />}
              </div>
              <div className="chat-msg-body">
                <div className="chat-msg-content">{msg.content}</div>
                {msg.metrics && (
                  <div className="chat-msg-metrics">
                    <span title="推理来源">
                      <Zap aria-hidden="true" size={12} />
                      {sourceLabel(msg.metrics.source)}
                    </span>
                    <span title="Token 数">
                      {formatNumber(msg.metrics.prompt_tokens + msg.metrics.completion_tokens)} tokens
                    </span>
                    <span title="耗时">{msg.metrics.duration_ms} ms</span>
                    <span title="预估费用">¥{microRmbToYuan(msg.metrics.price_micro_rmb)}</span>
                    <span title="GPU 能耗">{microWhToWh(msg.metrics.energy_micro_wh)} Wh</span>
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
        {chatMutation.isPending && (
          <div className="chat-msg assistant">
            <div className="chat-msg-avatar">
              <Bot aria-hidden="true" size={18} />
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
        {chatMutation.isError && (
          <div className="chat-error">
            <ErrorState message={apiMessage(chatMutation.error)} />
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
          placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
          rows={1}
          disabled={chatMutation.isPending}
        />
        <button
          className="send-button"
          onClick={handleSend}
          disabled={!input.trim() || chatMutation.isPending || !effectiveModel}
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
