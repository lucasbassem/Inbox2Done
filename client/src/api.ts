export type Connection = { connected: boolean; email: string | null; display_name: string | null }
export type Billing = { plan: string; daily_limit: number; used_today: number; remaining_today: number; checkout_available: boolean; portal_available: boolean }
export type Thread = {
  id: number; subject: string; snippet: string; participants: string
  message_count: number; latest_message_at: string
}
export type ThreadPage = {
  items: Thread[]; total: number; page: number; total_pages: number
  has_next: boolean; has_previous: boolean
}
export type Message = { id: number; sender: string; sent_at: string | null; body_text: string; snippet: string }
export type ThreadDetail = Thread & { messages: Message[] }
export type Action = {
  id: number; title: string; description: string; owner: string | null
  due_at: string | null; priority: string; status: 'open' | 'in_progress' | 'completed'
}
export type Analysis = {
  id: number; summary: string; category: string; priority: string; created_at: string
  action_items: Action[]; suggested_replies: { id: number; tone: string; subject: string | null; body: string }[]
}
export type Job = {
  id: number; job_type: string; status: string; progress: number; error_message: string | null
  parameters: { thread_id?: number; max_threads?: number; force?: boolean }
}

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin', ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, body?.error ?? 'request_failed',
    body?.message ?? `Request failed (${response.status}). Please try again.`)
  return body as T
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}
export const isActive = (job: Job) => job.status === 'queued' || job.status === 'running'
