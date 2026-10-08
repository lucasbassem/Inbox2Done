import { expect, test } from '@playwright/test'

test.use({ timezoneId: 'America/New_York' })
test('today loads without AI; explicit batch analysis, tasks, cache and mobile work', async ({ page }) => {
  let connected = true
  let analyzed = false
  let completed = false
  let analysisRequests = 0
  let loads = 0
  let polls = 0
  const action = { id: 1, title: 'Review the homepage copy', description: 'Share final edits with Maya.', owner: 'You', due_at: '2026-10-09T17:00:00Z', priority: 'high', status: 'open' }
  function job(status = 'completed') {
    return { id: 1, status, progress: status === 'completed' ? 100 : 15, parameters: { analyze: analyzed }, result: { date: '2026-10-07', time_zone: 'America/New_York', message_count: 1, thread_count: 1, analyzed_count: analyzed ? 1 : 0, failed_count: 0, items: [{ thread_id: 1, subject: 'Website launch - final review', participants: 'Maya Chen', snippet: 'Please review the homepage before Friday.', message_count: 1, error: null, analysis: analyzed ? { id: 1, summary: 'Maya needs your final review of the homepage copy before Friday.', priority: 'high', action_items: [{ ...action, status: completed ? 'completed' : 'open' }], suggested_replies: [{ id: 1, subject: 'Re: Website launch', body: 'Hi Maya, I will review the homepage before Friday.' }] } : null }] } }
  }
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    let body: unknown
    if (url.pathname === '/api/auth/google/status') body = { connected, email: 'alex@example.com', display_name: 'Alex Morgan' }
    else if (url.pathname === '/api/today') {
      expect(url.searchParams.get('time_zone')).toBe('America/New_York')
      if (url.searchParams.get('analyze') === 'true') { analyzed = true; analysisRequests++; polls = 0; body = job('queued') }
      else { loads++; body = job() }
    } else if (url.pathname === '/api/jobs/1') body = job(++polls > 1 ? 'completed' : 'running')
    else if (url.pathname === '/api/actions/1') { completed = route.request().postDataJSON().status === 'completed'; body = { ...action, status: completed ? 'completed' : 'open' } }
    else if (url.pathname === '/api/auth/google/logout') { connected = false; body = { connected: false } }
    else throw new Error(`Unexpected request ${url.pathname}`)
    await route.fulfill({ json: body })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Your inbox is ready.' })).toBeVisible()
  expect(analysisRequests).toBe(0)
  expect(loads).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Analyze today’s inbox' }).click()
  await expect(page.getByRole('button', { name: 'Analyze today’s inbox' })).toBeDisabled()
  await expect(page.getByRole('checkbox')).toBeEnabled({ timeout: 15000 })
  expect(analysisRequests).toBe(1)
  await expect(page.getByRole('heading', { name: 'What matters today' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Website launch - final review' })).toHaveCount(0)
  await page.getByRole('checkbox').click()
  await expect(page.getByRole('checkbox')).toBeChecked()
  await page.reload()
  await expect(page.getByRole('checkbox')).toBeChecked()
  expect(analysisRequests).toBe(1)
  await page.getByRole('checkbox').click()
  await expect(page.getByRole('checkbox')).not.toBeChecked()
  await page.getByText('Suggested replies', { exact: true }).click()
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByRole('button', { name: 'Copy reply' }).click()
  await expect(page.getByRole('button', { name: 'Copied' })).toBeVisible()
  await page.screenshot({ path: 'test-results/today-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/today-mobile.png', fullPage: true })
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('link', { name: /Connect with Google/ })).toBeVisible()
})
