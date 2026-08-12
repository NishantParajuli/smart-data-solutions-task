import { FormEvent, useEffect, useMemo, useState } from 'react'
import { ask, getDocuments } from './api'
import type { Document, Evidence, QueryResponse } from './types'

const suggestions = [
  "What drove Apple's Services growth in Q3 2022?",
  'What were Products and Services gross margin percentages?',
  'How much cash came from operating activities in the first nine months?',
  'What manufacturing purchase obligations did Apple report?',
]

export default function App() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [selected, setSelected] = useState<Evidence | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [imageFailed, setImageFailed] = useState(false)
  const document = documents.find((item) => item.status === 'ready') || documents[0]

  useEffect(() => {
    getDocuments().then(setDocuments).catch((cause: Error) => setError(cause.message))
  }, [])

  const cited = useMemo(
    () => new Set(result?.citations.map((item) => item.evidence_id) || []),
    [result],
  )

  async function submit(event?: FormEvent, suggested?: string) {
    event?.preventDefault()
    const nextQuestion = suggested || question.trim()
    if (!nextQuestion || !document) return
    setQuestion(nextQuestion)
    setLoading(true)
    setError('')
    setSelected(null)
    try {
      const response = await ask(nextQuestion, document.id)
      setResult(response)
      const firstCitation = response.citations[0]?.evidence_id
      setSelected(
        response.retrieved_evidence.find((item) => item.evidence_id === firstCitation) ||
          response.retrieved_evidence[0] || null,
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The query failed')
    } finally {
      setLoading(false)
    }
  }

  function chooseEvidence(item: Evidence) {
    setSelected(item)
    setImageFailed(false)
  }

  return (
    <div className="app-shell">
      <header>
        <a className="brand" href="/">Filing<span>Evidence</span></a>
        <div className="document-status">
          <span className={document?.status === 'ready' ? 'dot ready' : 'dot'} />
          {document ? `${document.title} · ${document.page_count} pages` : 'No indexed filing'}
        </div>
      </header>

      <main>
        <section className="workspace">
          <div className="intro">
            <p className="eyebrow">APPLE · FORM 10-Q · Q3 2022</p>
            <h1>Ask the filing.<br /><em>Inspect the evidence.</em></h1>
            <p>Answers stay tied to the document. Every citation opens the exact PDF region.</p>
          </div>

          <form onSubmit={(event) => submit(event)} className="ask-box">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask about the narrative, a financial table, or a figure…"
              rows={3}
              disabled={loading}
            />
            <button disabled={loading || !document || question.trim().length < 3}>
              {loading ? 'Finding evidence…' : 'Ask the filing'}
            </button>
          </form>

          {!result && !loading && (
            <div className="suggestions">
              {suggestions.map((item) => (
                <button key={item} onClick={() => submit(undefined, item)}>{item}</button>
              ))}
            </div>
          )}

          {error && <div className="error">{error}</div>}
          {loading && <div className="loading"><span /><span /><span /> Retrieving and grounding</div>}

          {result && !loading && (
            <article className={`answer ${result.insufficient_evidence ? 'abstention' : ''}`}>
              <div className="answer-label">
                {result.insufficient_evidence ? 'INSUFFICIENT EVIDENCE' : 'GROUNDED ANSWER'}
              </div>
              <p>{result.answer}</p>
              {result.calculations.map((calculation) => (
                <div className="calculation" key={calculation.expression}>
                  <strong>{calculation.value}</strong><code>{calculation.expression}</code>
                </div>
              ))}
              {result.citations.length > 0 && (
                <div className="citation-row">
                  {result.citations.map((citation) => (
                    <button key={citation.evidence_id} onClick={() => {
                      const item = result.retrieved_evidence.find(
                        (evidence) => evidence.evidence_id === citation.evidence_id,
                      ); if (item) chooseEvidence(item)
                    }}>p. {citation.page}</button>
                  ))}
                </div>
              )}
            </article>
          )}

          {result && (
            <section className="evidence-list">
              <div className="section-title"><span>Retrieved evidence</span><small>PDF pages</small></div>
              {result.retrieved_evidence.map((item) => (
                <button
                  className={`evidence-card ${selected?.evidence_id === item.evidence_id ? 'active' : ''}`}
                  onClick={() => chooseEvidence(item)}
                  key={item.evidence_id}
                >
                  <span className="page">{item.page}</span>
                  <span><strong>{item.section.at(-1) || item.element_type}</strong>
                    <small>{item.content.slice(0, 145)}…</small></span>
                  {cited.has(item.evidence_id) && <span className="cited">CITED</span>}
                </button>
              ))}
              <details className="debug">
                <summary>Retrieval details</summary>
                <pre>{JSON.stringify(result.timings_ms, null, 2)}</pre>
              </details>
            </section>
          )}
        </section>

        <aside className={selected ? 'evidence-panel open' : 'evidence-panel'}>
          {selected ? (
            <>
              <div className="panel-head">
                <div><span>PRIMARY SOURCE</span><strong>PDF page {selected.page}</strong></div>
                <button onClick={() => setSelected(null)}>×</button>
              </div>
              <div className="crop">
                {selected.image_url && !imageFailed ? (
                  <img src={selected.image_url} onError={() => setImageFailed(true)} alt={`Evidence on page ${selected.page}`} />
                ) : <pre>{selected.content}</pre>}
              </div>
              <div className="panel-meta">
                <span>{selected.element_type}</span>
                <code>{selected.evidence_id}</code>
                <p>{selected.section.join(' › ') || 'Document body'}</p>
              </div>
            </>
          ) : <div className="panel-empty">Select evidence to inspect the source crop.</div>}
        </aside>
      </main>
    </div>
  )
}

