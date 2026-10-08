import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import App from './App'

const fetchMock = vi.fn()
let connected = true
let analyzed = false
let completed = false
let empty = false
const action = { id: 9, title: 'Review the draft', description: 'Send feedback', owner: 'You', due_at: null, priority: 'high', status: 'open' }
function result() {
  return { id: 1, status: 'completed', progress: 100, parameters: { analyze: analyzed }, result: { date: '2026-10-07', time_zone: 'America/New_York', message_count: empty ? 0 : 1, thread_count: empty ? 0 : 1, analyzed_count: analyzed ? 1 : 0, failed_count: 0, items: empty ? [] : [{ thread_id: 1, subject: 'Today’s review', participants: 'Maya', snippet: 'Please review the draft.', message_count: 1, error: null, analysis: analyzed ? { id: 1, summary: 'Maya needs feedback today.', priority: 'high', action_items: [{ ...action, status: completed ? 'completed' : 'open' }], suggested_replies: [{ id: 3, body: 'I will review it today.' }] } : null }] } }
}
beforeEach(() => {
  connected = true; analyzed = false; completed = false; empty = false
  fetchMock.mockReset()
  fetchMock.mockImplementation(async (url: string, options?: RequestInit) => {
    let body: unknown
    if (url === '/api/auth/google/status') body = { connected, email: 'you@example.com', display_name: 'Alex' }
    else if (url.startsWith('/api/today?')) { if (url.includes('analyze=true')) analyzed = true; body = result() }
    else if (url === '/api/actions/9') { completed = JSON.parse(String(options?.body)).status === 'completed'; body = { ...action, status: completed ? 'completed' : 'open' } }
    else if (url === '/api/auth/google/logout') { connected = false; body = { connected: false } }
    else throw new Error(`Unexpected request: ${url}`)
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
})
test('disconnected users only see Google login', async () => {
  connected = false; render(<App />)
  expect(await screen.findByRole('link', { name: /Connect with Google/ })).toBeVisible()
  expect(fetchMock.mock.calls.every(([url]) => url === '/api/auth/google/status')).toBe(true)
})
test('loading fetches today without requesting analysis', async () => {
  render(<App />)
  expect(await screen.findByRole('heading', { name: 'Your inbox is ready.' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Today’s review' })).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.some(([url]) => url.includes('analyze=false'))).toBe(true)
  expect(fetchMock.mock.calls.some(([url]) => url.includes('analyze=true'))).toBe(false)
})
test('only an explicit Analyze click requests AI analysis', async () => {
  render(<App />)
  await screen.findByRole('heading', { name: 'Your inbox is ready.' })
  fireEvent.click(screen.getByRole('button', { name: 'Analyze today’s inbox' }))
  expect(await screen.findByText('Maya needs feedback today.')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'What matters today' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Your action items' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Today’s review' })).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.filter(([url]) => url.includes('analyze=true'))).toHaveLength(1)
  fireEvent.click(screen.getByRole('checkbox'))
  await waitFor(() => expect(screen.getByRole('checkbox')).toBeChecked())
})
test('refresh only checks Gmail and displays saved results', async () => {
  analyzed = true; render(<App />)
  await screen.findByText('Maya needs feedback today.')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh today' }))
  expect(await screen.findByText('Maya needs feedback today.')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'What matters today' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Your action items' })).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Today’s review' })).not.toBeInTheDocument()
  expect(fetchMock.mock.calls.some(([url]) => url.includes('analyze=true'))).toBe(false)
})
test('empty today disables analysis', async () => {
  empty = true; render(<App />)
  expect(await screen.findByText('No Primary inbox emails today.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Analyze today’s inbox' })).toBeDisabled()
})
test('connection failure can be retried', async () => {
  fetchMock.mockRejectedValueOnce(new Error('Connection unavailable')); render(<App />)
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByRole('heading', { name: 'Your inbox is ready.' })).toBeVisible()
})
test('sign out stops showing the inbox', async () => {
  render(<App />); await screen.findByRole('heading', { name: 'Your inbox is ready.' })
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(await screen.findByRole('link', { name: /Connect with Google/ })).toBeVisible()
})
