import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  ExternalLink,
  Lock,
  Save,
  Settings as SettingsIcon,
  Shield,
  ShieldAlert,
  X,
} from 'lucide-react'
import { useState } from 'react'

import { api, apiMessage, type CloudApiSettings } from '../api/client'
import { ErrorState, LoadingState } from '../components/PageState'
import { PageHeader } from '../components/PageHeader'

const PROVIDER_LINKS: Record<string, string> = {
  openai: 'https://platform.openai.com/api-keys',
  anthropic: 'https://console.anthropic.com/',
  deepseek: 'https://platform.deepseek.com/',
  alibaba: 'https://help.aliyun.com/zh/model-studio/',
  bytedance: 'https://www.volcengine.com/product/doubao',
  google: 'https://aistudio.google.com/apikey',
}

const PROVIDER_PLACEHOLDERS: Record<string, string> = {
  openai: 'sk-...',
  anthropic: 'sk-ant-...',
  deepseek: 'sk-...',
  alibaba: 'sk-...',
  bytedance: '火山引擎 API Key',
  google: 'AIza...',
}

const TOKEN_STORAGE_KEY = 'greenflex_admin_token'

export function SettingsPage() {
  const queryClient = useQueryClient()
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({})
  const [savedProvider, setSavedProvider] = useState<string | null>(null)
  const [adminToken, setAdminToken] = useState(
    () => sessionStorage.getItem(TOKEN_STORAGE_KEY) ?? '',
  )
  const [tokenInput, setTokenInput] = useState('')
  const [tokenVerified, setTokenVerified] = useState<boolean | null>(null)

  const settings = useQuery<CloudApiSettings>({
    queryKey: ['cloud-settings'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/settings/cloud-api')
      if (error) throw new Error(apiMessage(error))
      return data as CloudApiSettings
    },
  })

  // Verify admin token
  const verifyToken = async (token: string): Promise<boolean> => {
    const { data } = await api.GET('/api/v1/settings/admin-token-status', {
      headers: token ? { 'X-Admin-Token': token } : {},
    })
    const valid = (data as { valid: boolean } | undefined)?.valid ?? false
    setTokenVerified(valid)
    if (valid) {
      sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
      setAdminToken(token)
    }
    return valid
  }

  // Verify on mount if we have a stored token
  useState(() => {
    if (adminToken) {
      void verifyToken(adminToken)
    }
  })

  const handleTokenSubmit = () => {
    if (tokenInput.trim()) {
      void verifyToken(tokenInput.trim())
    }
  }

  const saveMutation = useMutation<CloudApiSettings, Error, { provider: string; key: string }>({
    mutationFn: async ({ provider, key }: { provider: string; key: string }) => {
      const body: Record<string, string> = {}
      body[`${provider}_api_key`] = key
      const { data, error } = await api.PUT('/api/v1/settings/cloud-api', {
        body,
        headers: adminToken ? { 'X-Admin-Token': adminToken } : {},
      })
      if (error) {
        const msg = apiMessage(error)
        if (msg.includes('管理员令牌') || msg.includes('admin_token')) {
          setTokenVerified(false)
        }
        throw new Error(msg)
      }
      return data
    },
    onSuccess: (_data, variables) => {
      setSavedProvider(variables.provider)
      setKeyInputs((prev) => ({ ...prev, [variables.provider]: '' }))
      setTimeout(() => setSavedProvider(null), 2000)
      void queryClient.invalidateQueries({ queryKey: ['cloud-settings'] })
    },
  })

  const clearMutation = useMutation<CloudApiSettings, Error, string>({
    mutationFn: async (provider: string) => {
      const body: Record<string, string> = { [`${provider}_api_key`]: '' }
      const { data, error } = await api.PUT('/api/v1/settings/cloud-api', {
        body,
        headers: adminToken ? { 'X-Admin-Token': adminToken } : {},
      })
      if (error) throw new Error(apiMessage(error))
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cloud-settings'] })
    },
  })

  const needsAuth = tokenVerified === false || (!adminToken && settings.data)

  return (
    <main className="page">
      <PageHeader
        eyebrow="系统设置"
        title="云 API 配置"
        actions={
          <span className="settings-hint">
            <Shield aria-hidden="true" size={14} />
            密钥加密存储，仅本机访问
          </span>
        }
      />

      {/* Admin token gate */}
      {needsAuth && (
        <div className="token-gate">
          <Lock aria-hidden="true" size={20} />
          <div>
            <strong>需要管理员令牌</strong>
            <p>
              首次使用时，后端启动日志中会显示管理员令牌。也可在{' '}
              <code>artifacts/admin_token.txt</code> 文件中找到。
            </p>
          </div>
          <div className="token-input-row">
            <input
              type="password"
              placeholder="粘贴管理员令牌..."
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleTokenSubmit()}
            />
            <button className="primary-button-sm" onClick={handleTokenSubmit}>
              验证
            </button>
          </div>
          {tokenVerified === false && <p className="field-error">令牌无效，请重新输入。</p>}
        </div>
      )}

      {settings.isLoading && <LoadingState label="加载配置" />}
      {settings.isError && <ErrorState message={apiMessage(settings.error)} />}

      {settings.data && !needsAuth && (
        <div className="settings-grid">
          {settings.data.providers.map((p) => (
            <div key={p.provider} className={`settings-card ${p.configured ? 'configured' : ''}`}>
              <div className="settings-card-header">
                <div>
                  <strong>{p.label}</strong>
                  {p.configured && p.key_preview && (
                    <span className="key-preview">
                      <Check aria-hidden="true" size={12} />
                      {p.key_preview}
                    </span>
                  )}
                </div>
                <a
                  href={PROVIDER_LINKS[p.provider]}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link-button"
                  title="获取 API Key"
                >
                  <ExternalLink aria-hidden="true" size={14} />
                </a>
              </div>
              <div className="settings-card-body">
                <input
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={
                    p.configured ? '已配置，输入新密钥可更新' : PROVIDER_PLACEHOLDERS[p.provider] ?? '输入 API Key'
                  }
                  value={keyInputs[p.provider] ?? ''}
                  onChange={(e) =>
                    setKeyInputs((prev) => ({ ...prev, [p.provider]: e.target.value }))
                  }
                  onKeyDown={(e) => {
                    const val = keyInputs[p.provider]?.trim()
                    if (e.key === 'Enter' && val) {
                      saveMutation.mutate({
                        provider: p.provider,
                        key: val,
                      })
                    }
                  }}
                />
                <div className="settings-card-actions">
                  <button
                    className="primary-button-sm"
                    disabled={!keyInputs[p.provider]?.trim() || saveMutation.isPending}
                    onClick={() => {
                      const val = keyInputs[p.provider]?.trim()
                      if (val) saveMutation.mutate({ provider: p.provider, key: val })
                    }}
                  >
                    {savedProvider === p.provider ? (
                      <Check aria-hidden="true" size={14} />
                    ) : (
                      <Save aria-hidden="true" size={14} />
                    )}
                    {savedProvider === p.provider ? '已保存' : '保存'}
                  </button>
                  {p.configured && (
                    <button
                      className="ghost-button-sm"
                      disabled={clearMutation.isPending}
                      onClick={() => clearMutation.mutate(p.provider)}
                    >
                      <X aria-hidden="true" size={14} />
                      清除
                    </button>
                  )}
                </div>
              </div>
              {saveMutation.isError && saveMutation.variables?.provider === p.provider && (
                <p className="field-error">{apiMessage(saveMutation.error)}</p>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="settings-info">
        <h3>
          <ShieldAlert aria-hidden="true" size={16} />
          安全说明
        </h3>
        <ul>
          <li>
            <strong>传输安全：</strong>后端仅绑定 127.0.0.1，API Key 不会经过外网传输到云服务商以外的地方。
          </li>
          <li>
            <strong>存储安全：</strong>密钥保存在服务器本地{' '}
            <code>artifacts/runtime_settings.json</code>，文件权限仅限当前用户读取。
          </li>
          <li>
            <strong>接口保护：</strong>修改设置需要管理员令牌（首次启动自动生成，见{' '}
            <code>artifacts/admin_token.txt</code>）。
          </li>
          <li>
            <strong>脱敏显示：</strong>界面只显示密钥前 4 位和后 4 位（如{' '}
            <code>sk-***abcd</code>），不返回完整密钥。
          </li>
          <li>
            <strong>日志防护：</strong>系统日志自动过滤 API Key 等敏感字段，不会明文记录。
          </li>
          <li>
            <strong>速率限制：</strong>设置接口每分钟最多 10 次请求，防止暴力破解。
          </li>
          <li>
            <strong>生产建议：</strong>如需暴露到外网，请在反向代理层启用 HTTPS 和额外认证。
          </li>
        </ul>
        <h3 style={{ marginTop: 18 }}>
          <SettingsIcon aria-hidden="true" size={16} />
          使用说明
        </h3>
        <ul>
          <li>配置 API Key 后，在 <strong>AI 对话</strong> 或 <strong>模型试跑</strong> 中选择对应云端模型即可真实调用。</li>
          <li>未配置 Key 的云端模型会自动回退到<strong>模拟推理</strong>，不影响功能体验。</li>
          <li>也可通过 <code>.env</code> 文件配置（环境变量优先级低于界面设置）。</li>
        </ul>
      </div>
    </main>
  )
}
