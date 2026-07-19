import { expect, test } from '@playwright/test'

const models = [
  {
    id: 'qwen2.5-1.5b-q4',
    display_name: 'Qwen2.5 1.5B',
    runtime_name: 'qwen2.5:1.5b',
    tier: 'balanced',
    parameter_b: '1.5B',
    context_limit: 4096,
    recommended_for: ['摘要'],
    input_rate_rmb_per_million: '0.300000',
    output_rate_rmb_per_million: '0.800000',
    available: false,
    availability_detail: '未安装或运行时离线',
    rate_provenance: 'simulated',
  },
]

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/models', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(models) })
  })
})

test('workspace remains usable without horizontal overflow', async ({ page }, testInfo) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '创建绿色推理订单' })).toBeVisible()
  const dimensions = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    tierControl: (() => {
      const control = document.querySelector('.segmented.three')
      if (!control) return null
      const bounds = control.getBoundingClientRect()
      const items = Array.from(control.querySelectorAll('label span')).map((item) => {
        const itemBounds = item.getBoundingClientRect()
        return { left: itemBounds.left, right: itemBounds.right }
      })
      return {
        left: bounds.left,
        right: bounds.right,
        scrollWidth: control.scrollWidth,
        clientWidth: control.clientWidth,
        items,
      }
    })(),
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.innerWidth)
  const tierControl = dimensions.tierControl
  if (!tierControl) throw new Error('Tier control is missing.')
  expect(tierControl.scrollWidth).toBeLessThanOrEqual(tierControl.clientWidth)
  for (const item of tierControl.items) {
    expect(item.left).toBeGreaterThanOrEqual(tierControl.left)
    expect(item.right).toBeLessThanOrEqual(tierControl.right)
  }
  await page.screenshot({ path: testInfo.outputPath('workspace.png'), fullPage: true })
})

test('mobile menu opens without exposing the closed sidebar', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'mobile-only assertion')
  await page.goto('/')
  const sidebar = page.locator('.sidebar')
  await expect(sidebar).toBeHidden()
  await page.getByRole('button', { name: '打开菜单' }).click()
  await expect(sidebar).toBeVisible()
  await page.locator('.sidebar').getByRole('button', { name: '关闭菜单' }).click()
  await expect(sidebar).toBeHidden()
})

test('preview reports the real model-offline state', async ({ page }) => {
  await page.goto('/preview')
  await expect(page.getByText(/未检测到可用模型/)).toBeVisible()
  await expect(page.getByRole('button', { name: '运行 0 个模型' })).toBeDisabled()
})
