import { useEffect, useRef, useState } from 'react'
import { api, errorMessage } from './api'
import type { Action, Analysis, Connection } from './api'

type Item = { thread_id: number; subject: string; participants: string; snippet: string; message_count: number; analysis: Analysis | null; error: string | null }
type Result = { date: string; time_zone: string; message_count: number; thread_count: number; analyzed_count: number; failed_count: number; items: Item[] }
type TodayJob = { id: number; status: string; progress: number; parameters: { analyze: boolean }; result: Result | null; error_message: string | null }
const localClock = () => `${new Date().toLocaleDateString('en-CA')}|${Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'}`

export default function Today(props: { connection: Connection; logout: () => void }) {
  const [clock, setClock] = useState(localClock)
  useEffect(() => {
    const update = () => setClock(localClock())
    const timer = setInterval(update, 30000)
    window.addEventListener('focus', update)
    return () => { clearInterval(timer); window.removeEventListener('focus', update) }
  }, [])
  return <TodayInbox key={clock} {...props} timeZone={clock.split('|')[1]} />
}

function TodayInbox({ connection, logout, timeZone }: { connection: Connection; logout: () => void; timeZone: string }) {
  const [job, setJob] = useState<TodayJob | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [pending, setPending] = useState<number | null>(null)
  const [copied, setCopied] = useState<number | null>(null)
  const controller = useRef<AbortController | null>(null)
  async function load(analyze: boolean, zone: string) {
    controller.current?.abort()
    const request = new AbortController()
    controller.current = request
    try {
      let next = await api<TodayJob>(`/today?time_zone=${encodeURIComponent(zone)}&analyze=${analyze}`, { method: 'POST', signal: request.signal })
      while (!request.signal.aborted) {
        setJob(next)
        if (!['queued', 'running'].includes(next.status)) break
        await new Promise(resolve => setTimeout(resolve, 1500))
        if (request.signal.aborted) return
        next = await api<TodayJob>(`/jobs/${next.id}`, { signal: request.signal })
      }
    } catch (cause) { if (!request.signal.aborted) setError(errorMessage(cause)) }
    finally { if (!request.signal.aborted) setBusy(false) }
  }
  useEffect(() => {
    // Page loads fetch Gmail only. Analysis requires an explicit button click.
    // load updates React state only after awaiting the network response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(false, timeZone)
    return () => controller.current?.abort()
  }, [timeZone])
  function start(analyze: boolean) {
    setBusy(true); setError(''); setJob(null)
    void load(analyze, timeZone)
  }
  async function updateAction(action: Action) {
    setPending(action.id)
    try {
      const updated = await api<Action>(`/actions/${action.id}`, { method: 'PATCH', body: JSON.stringify({ status: action.status === 'completed' ? 'open' : 'completed' }) })
      setJob(current => current?.result ? { ...current, result: { ...current.result, items: current.result.items.map(item => item.analysis ? { ...item, analysis: { ...item.analysis, action_items: item.analysis.action_items.map(old => old.id === updated.id ? updated : old) } } : item) } } : current)
    } catch (cause) { setError(errorMessage(cause)) }
    finally { setPending(null) }
  }
  async function copyReply(id: number, body: string) {
    try { await navigator.clipboard.writeText(body); setCopied(id) }
    catch { setError('Copy is unavailable. Select the reply text and copy it manually.') }
  }
  async function signOut() {
    try { await api('/auth/google/logout', { method: 'POST' }); logout() }
    catch (cause) { setError(errorMessage(cause)) }
  }
  const result = job?.result
  const rank = (priority: string) => ({ urgent: 0, high: 1, medium: 2, low: 3 }[priority] ?? 2)
  const reviewed = (result?.items ?? []).filter(item => item.analysis)
    .sort((a, b) => rank(a.analysis!.priority) - rank(b.analysis!.priority))
  const important = reviewed.filter(item => item.analysis!.action_items.length > 0 || rank(item.analysis!.priority) < 2)
  const summaries = [...new Set((important.length ? important : reviewed).map(item => item.analysis!.summary.trim()))]
  const actions = reviewed.flatMap(item => item.analysis!.action_items.map(action => ({ action, source: item.subject })))
    .sort((a, b) => Number(a.action.status === 'completed') - Number(b.action.status === 'completed') || rank(a.action.priority) - rank(b.action.priority) || (a.action.due_at ?? '9999').localeCompare(b.action.due_at ?? '9999'))
  const replies = reviewed.flatMap(item => item.analysis!.suggested_replies)
  const completedCount = actions.filter(({ action }) => action.status === 'completed').length
  return <div className="app-shell">
    <aside className="sidebar"><a className="brand" href="/"><span className="brand-mark">✓</span>Inbox2Done<span className="brand-dot">.</span></a>
      <div className="sidebar-label">YOUR WORKSPACE</div><div className="nav-active">Today’s inbox <span className="nav-count">{result?.message_count ?? '—'}</span></div>
      <div className="sidebar-note"><span>ONE DAY AT A TIME.</span><p>A little clarity.<br />A lot less inbox.</p></div>
      <div className="account"><span className="avatar">{(connection.display_name || 'U').charAt(0)}</span><div><strong>{connection.display_name}</strong><span>{connection.email}</span></div></div>
      <button className="quiet signout" onClick={() => void signOut()}>Sign out</button>
    </aside>
    <main className="workspace briefing-workspace"><header className="page-header"><div><div className="eyebrow">YOUR PRIMARY INBOX · TODAY ONLY</div><h1>Your daily briefing.</h1><p className="muted">{result?.date ?? new Date().toLocaleDateString()} · {timeZone}</p></div>
      <div className="today-controls"><button className="quiet" disabled={busy} onClick={() => start(false)}>Refresh today</button><button disabled={busy || !result?.message_count} onClick={() => start(true)}>Analyze today’s inbox</button></div></header>
      <p className="today-explainer">A quick read of what matters, followed by what to do next. Analysis sends today’s Primary email text to OpenAI only when you click Analyze.</p>
      {(error || job?.error_message) && <div className="notice" role="alert"><span>{error || job?.error_message}</span><button className="quiet" onClick={() => start(false)}>Try again</button></div>}
      {busy && <section className="today-progress" role="status"><strong>{job?.parameters.analyze ? 'Analyzing today’s emails…' : 'Finding today’s Primary inbox emails…'}</strong><progress aria-label="Today progress" value={job?.progress ?? 0} max={100} /><span>{result ? `${result.analyzed_count} of ${result.thread_count} conversations analyzed` : 'Checking Gmail'}</span></section>}
      {!busy && result?.message_count === 0 && <section className="briefing-empty"><span className="briefing-spark">✦</span><h2>No Primary inbox emails today.</h2><p>Refresh later to check for new arrivals.</p></section>}
      {!busy && !!result?.message_count && reviewed.length === 0 && <section className="briefing-empty"><span className="briefing-spark">✦</span><h2>Your inbox is ready.</h2><p>{result.message_count} {result.message_count === 1 ? 'email' : 'emails'} from today. One click turns them into the important points and a clear action list.</p><p className="muted small">Click Analyze today’s inbox above to prepare your briefing.</p></section>}
      {!!reviewed.length && <article className="daily-briefing" aria-label="Daily briefing">
        <div className="briefing-byline"><span className="briefing-spark">✦</span><strong>Inbox2Done</strong><span>Today’s briefing</span></div>
        <p className="briefing-intro">Here’s what needs your attention today.</p>
        <section aria-labelledby="briefing-summary"><h2 id="briefing-summary">What matters today</h2>
          <ul className="briefing-highlights">{summaries.slice(0, 4).map(summary => <li key={summary}>{summary}</li>)}</ul>
          {summaries.length > 4 && <details className="briefing-more"><summary>{summaries.length - 4} more updates</summary><ul className="briefing-highlights">{summaries.slice(4).map(summary => <li key={summary}>{summary}</li>)}</ul></details>}
          {reviewed.length > important.length && important.length > 0 && <p className="briefing-context">{reviewed.length - important.length} other reviewed {reviewed.length - important.length === 1 ? 'conversation has' : 'conversations have'} no identified action and lower priority.</p>}
        </section>
        <section aria-labelledby="briefing-actions"><div className="section-heading"><h2 id="briefing-actions">Your action items</h2>{actions.length > 0 && <span className="muted small">{completedCount}/{actions.length} done</span>}</div>
          {actions.length === 0 ? <p>No action items were identified in the emails reviewed.</p> : <ul className="actions briefing-actions">{actions.map(({ action, source }) => <li key={action.id} className={action.status === 'completed' ? 'done' : ''}>
            <input type="checkbox" aria-label={`Complete ${action.title}`} checked={action.status === 'completed'} disabled={busy || pending !== null} onChange={() => void updateAction(action)} />
            <div><strong>{action.title}</strong>{action.description && <p>{action.description}</p>}<div className="action-meta"><span className={`badge ${action.priority}`}>{action.priority}</span>{action.owner && <span>{action.owner}</span>}{action.due_at && <span>Due {new Date(action.due_at).toLocaleString()}</span>}</div><details className="action-source"><summary>Source email</summary><span>{source || '(No subject)'}</span></details></div>
          </li>)}</ul>}
        </section>
        {replies.length > 0 && <details className="source"><summary>Suggested replies</summary>{replies.map(reply => <div className="reply" key={reply.id}><div className="section-heading"><strong>{reply.subject || 'Reply draft'}</strong><button className="quiet" onClick={() => void copyReply(reply.id, reply.body)}>{copied === reply.id ? 'Copied' : 'Copy reply'}</button></div><p className="prewrap">{reply.body}</p></div>)}</details>}
        <p className="briefing-coverage">Reviewed {reviewed.length} of {result?.thread_count} conversations across {result?.message_count} emails from today’s Primary inbox.{busy ? ' The briefing is still being prepared.' : ''}</p>
      </article>}
      {!!result?.failed_count && <div className="notice" role="alert">{result.failed_count} conversations could not be analyzed. Click Analyze today’s inbox to retry; completed results are saved.</div>}
      {!busy && !!result && result.analyzed_count < result.thread_count && result.failed_count === 0 && reviewed.length > 0 && <p className="briefing-context">New or changed emails are waiting. Click Analyze today’s inbox to update this briefing.</p>}
      <footer>Read-only Gmail access · Replies are never sent automatically</footer>
    </main>
  </div>
}
