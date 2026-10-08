import { useEffect, useState } from 'react'
import { api, errorMessage } from './api'
import type { Connection } from './api'
import Today from './Today'
import './App.css'
function Notice({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="notice" role="alert"><span>{message}</span>{retry && <button className="quiet" onClick={retry}>Try again</button>}</div>
}
export default function App() {
  const [connection, setConnection] = useState<Connection | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    api<Connection>('/auth/google/status', { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) { setConnection(value); setError('') } })
      .catch(error => { if (!controller.signal.aborted) setError(errorMessage(error)) })
    return () => controller.abort()
  }, [retry])

  if (connection?.connected) return <Today connection={connection} logout={() => setConnection({ connected: false, email: null, display_name: null })} />
  return <main className="welcome"><a className="brand" href="/"><span className="brand-mark">✓</span>Inbox2Done<span className="brand-dot">.</span></a>
    <section className="welcome-content"><div className="eyebrow">A CLEARER WAY THROUGH YOUR DAY</div><h1>Your inbox has enough.<br /><em>Take back your focus.</em></h1>
      <p>Find today’s Primary inbox emails. Turn them into a plan.<br />Leave with a little less on your mind.</p>
      {error ? <Notice message={error} retry={() => setRetry(value => value + 1)} /> : !connection ? <p role="status">Checking your connection…</p> : <a className="button connect" href="/api/auth/google/login">Connect with Google <span>↗</span></a>}
      <div className="welcome-features"><div><span>01</span><h2>See what matters</h2><p>Clear summaries, without the scroll.</p></div><div><span>02</span><h2>Know your next move</h2><p>Tasks, owners, and deadlines in one place.</p></div><div><span>03</span><h2>Make it done</h2><p>Check off tasks and start replies faster.</p></div></div>
      <p className="small muted">Gmail access is read-only. Today’s email text is sent to OpenAI only when you click Analyze today’s inbox.<br />Inbox2Done never sends or deletes your email.</p>
    </section>
  </main>
}
