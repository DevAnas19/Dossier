import { useEffect, useRef, useState } from 'react'
import { startResearch, getResearchStatus } from './api'

const STAGES = [
  { id: 1, label: 'Plan' },
  { id: 2, label: 'Research' },
  { id: 3, label: 'Extract claims' },
  { id: 4, label: 'Verify claims' },
  { id: 5, label: 'Draft report' },
  { id: 6, label: 'Review' },
]

// Markdown-ish renderer for the LLM output: headers, bold, lists, and tables.
function isTableRow(line) {
  return /^\|.*\|$/.test(line.trim())
}
function isTableSeparator(line) {
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(line.trim())
}
function splitTableRow(line) {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((c) => c.trim())
}

function renderReport(text) {
  if (!text) return null
  const lines = text.split('\n')
  const blocks = []
  let listBuffer = []
  let i = 0

  const flushList = (key) => {
    if (listBuffer.length) {
      blocks.push(
        <ul className="report-list" key={`ul-${key}`}>
          {listBuffer.map((item, idx) => (
            <li key={idx}>{renderInline(item)}</li>
          ))}
        </ul>
      )
      listBuffer = []
    }
  }

  while (i < lines.length) {
    const raw = lines[i]
    const line = raw.trim()

    if (!line) { flushList(i); i++; continue }

    // Table: header row + separator row + body rows
    if (isTableRow(line) && lines[i + 1] && isTableSeparator(lines[i + 1])) {
      flushList(i)
      const headerCells = splitTableRow(line)
      const rows = []
      i += 2
      while (i < lines.length && isTableRow(lines[i].trim())) {
        rows.push(splitTableRow(lines[i]))
        i++
      }
      blocks.push(
        <div className="report-table-wrap" key={`table-${i}`}>
          <table className="report-table">
            <thead>
              <tr>{headerCells.map((c, ci) => <th key={ci}>{renderInline(c)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => <td key={ci}>{renderInline(cell)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      continue
    }

    const headerMatch = line.match(/^(#{1,3})\s+(.*)/)
    const listMatch = line.match(/^[-*]\s+(.*)/)
    const numberedHeaderMatch = line.match(/^(\d+)\.\s+([A-Za-z][A-Za-z\s]{0,40})$/)

    if (headerMatch) {
      flushList(i)
      const level = headerMatch[1].length
      const Tag = level === 1 ? 'h2' : level === 2 ? 'h3' : 'h4'
      blocks.push(<Tag key={i} className="report-heading">{renderInline(headerMatch[2])}</Tag>)
    } else if (numberedHeaderMatch) {
      flushList(i)
      blocks.push(<h3 key={i} className="report-heading">{numberedHeaderMatch[1]}. {renderInline(numberedHeaderMatch[2])}</h3>)
    } else if (listMatch) {
      listBuffer.push(listMatch[1])
    } else {
      flushList(i)
      blocks.push(<p key={i} className="report-p">{renderInline(line)}</p>)
    }
    i++
  }
  flushList('end')
  return blocks
}

function renderInline(text) {
  // Defensive: some models emit literal <br> tags despite instructions not to.
  const brSplit = text.split(/<br\s*\/?>/gi)
  return brSplit.map((segment, si) => (
    <span key={si}>
      {si > 0 && <br />}
      {renderBold(segment)}
    </span>
  ))
}

function renderBold(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

function countSources(text) {
  if (!text) return 0
  const matches = text.match(/https?:\/\/[^\s)\]]+/g)
  return matches ? new Set(matches).size : 0
}

function countWords(text) {
  if (!text) return 0
  return text.trim().split(/\s+/).length
}

export default function App() {
  const [topic, setTopic] = useState('')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [caseNo] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}-${String(d.getHours()).padStart(2, '0')}${String(d.getMinutes()).padStart(2, '0')}`
  })
  const pollRef = useRef(null)

  useEffect(() => {
    return () => clearInterval(pollRef.current)
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!topic.trim() || submitting) return

    setError('')
    setJob(null)
    setSubmitting(true)

    try {
      const { job_id } = await startResearch(topic.trim())
      pollRef.current = setInterval(async () => {
        try {
          const data = await getResearchStatus(job_id)
          setJob(data)
          if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(pollRef.current)
            setSubmitting(false)
          }
        } catch (err) {
          clearInterval(pollRef.current)
          setError(err.message)
          setSubmitting(false)
        }
      }, 1200)
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  const currentStage = job?.stage || 0
  const isRunning = job?.status === 'running'
  const isFailed = job?.status === 'failed'
  const isDone = job?.status === 'completed'

  return (
    <div className="page">
      <header className="masthead">
        <div className="masthead-inner">
          <span className="wordmark">Dossier</span>
          <span className="masthead-tag">— an autonomous research desk</span>
        </div>
      </header>

      <section className="control">
        <form className="topic-form" onSubmit={handleSubmit}>
          <label htmlFor="topic" className="topic-label">Assign a topic</label>
          <div className="topic-row">
            <input
              id="topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. quantum error correction"
              disabled={submitting}
            />
            <button type="submit" disabled={submitting || !topic.trim()}>
              {submitting ? 'Working' : 'Dispatch'}
            </button>
          </div>
        </form>

        {job && (
          <ol className="ticker">
            {STAGES.map((s) => {
              let state = 'pending'
              if (isFailed && s.id === currentStage) state = 'error'
              else if (s.id < currentStage) state = 'done'
              else if (s.id === currentStage) state = job.stage_status === 'done' ? 'done' : 'active'
              return (
                <li key={s.id} className={`ticker-item ticker-${state}`}>
                  <span className="ticker-num">{String(s.id).padStart(2, '0')}</span>
                  <span className="ticker-label">{s.label}</span>
                  <span className="ticker-dot" aria-hidden="true" />
                </li>
              )
            })}
          </ol>
        )}

        {error && <p className="error-text">Dispatch failed: {error}</p>}
        {isFailed && job?.error && <p className="error-text">Pipeline error: {job.error}</p>}
      </section>

      {!job && (
        <section className="empty-hero">
          <div className="empty-hero-inner">
            <span className="empty-hero-kicker">How it works</span>
            <ol className="empty-hero-steps">
              <li><strong>Plan</strong> — breaks your topic into focused sub-questions</li>
              <li><strong>Research</strong> — web + academic sources searched in parallel per sub-question</li>
              <li><strong>Extract</strong> — pulls discrete, checkable claims out of all the evidence</li>
              <li><strong>Verify</strong> — each claim is scored against the evidence; missing ones are re-researched</li>
              <li><strong>Draft</strong> — a writer turns verified findings into a structured report</li>
              <li><strong>Review</strong> — a critic checks for gaps before you see it</li>
            </ol>
          </div>
        </section>
      )}

      {isRunning && !job?.report && (
        <p className="hint-text">
          {job?.stage_name || 'Starting up'} — this can take a minute or two per source.
        </p>
      )}

      {isDone && (
        <section className="document-wrap">
          <article className="page-sheet">
            <div className="page-sheet-head">
              <span className="page-sheet-eyebrow">Case No. {caseNo}</span>
              <h1>{job.topic}</h1>
              <div className="page-sheet-stats">
                <span>{countWords(job.report)} words</span>
                <span className="stat-sep">·</span>
                <span>{countSources(job.report)} sources cited</span>
              </div>
              {job.claim_summary && (
                <div className="claim-summary">
                  <span className="claim-badge claim-supported">
                    ✓ {job.claim_summary.supported ?? 0} supported
                  </span>
                  <span className="claim-badge claim-contradicted">
                    ✕ {job.claim_summary.contradicted ?? 0} contradicted
                  </span>
                  <span className="claim-badge claim-unresolved">
                    ◌ {job.claim_summary.unresolved ?? 0} unresolved
                  </span>
                </div>
              )}
            </div>
            <div className="page-sheet-body">
              {renderReport(job.report)}
            </div>
          </article>

          <aside className="review-slip">
            <span className="review-slip-label">Editor's review</span>
            <div className="review-slip-body">
              {renderReport(job.feedback)}
            </div>
          </aside>
        </section>
      )}
    </div>
  )
}