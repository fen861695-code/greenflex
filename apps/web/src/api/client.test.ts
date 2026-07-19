import { describe, expect, it } from 'vitest'

import { apiMessage } from './client'

describe('API error messages', () => {
  it('uses safe server messages and validation fallbacks', () => {
    expect(apiMessage({ message: '模型未安装' })).toBe('模型未安装')
    expect(apiMessage({ detail: [] })).toBe('提交内容不符合接口约束，请检查字段和长度。')
    expect(apiMessage(null)).toBe('请求未完成，请确认本地 API 正在运行。')
  })
})
