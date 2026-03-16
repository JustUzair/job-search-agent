import { useState, useEffect, useCallback } from 'react'
import { getJobs, setJobStatus, startScrape, getScrapeStatus, getBatches, pollBatches } from '../api.js'
import TailorModal from './TailorModal.jsx'
import JobDetailModal from './JobDetailModal.jsx'

const SCORE_DOT = (score) => {
  if (score >= 75) return 'bg-emerald-500'
  if (score >= 55) return 'bg-amber-400'
  return 'bg-red-500'
}

const SCORE_TEXT = (score) => {
  if (score >= 75) return 'text-emerald-400'
  if (score >= 55) return 'text-amber-400'
  return 'text-red-400'
}

export function WorkTypeBadge({ type }) {
  const map = {
    remote: 'bg-emerald-900 text-emerald-300',
    hybrid: 'bg-amber-900 text-amber-300',
    onsite: 'bg-slate-700 text-slate-300'
  }
  const cls = map[type] || map.onsite
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {type || 'unknown'}
    </span>
  )
}

function JobCard({ job, onSkip, onTailor, onClick }) {
  return (
    <div
      onClick={onClick}
      className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition-colors cursor-pointer"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex-shrink-0 flex flex-col items-center gap-1">
            <div className={`w-3 h-3 rounded-full ${SCORE_DOT(job.score)}`} />
            <span className={`text-sm font-bold ${SCORE_TEXT(job.score)}`}>{job.score ?? '?'}</span>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-white truncate">{job.title}</span>
              <WorkTypeBadge type={job.work_type} />
            </div>
            <div className="text-slate-400 text-sm mt-0.5">
              {job.company}
              <span className="mx-2 text-slate-600">·</span>
              <span className="text-slate-500">{job.source}</span>
              <span className="mx-2 text-slate-600">·</span>
              <span className="text-slate-500">{job.found_at ? new Date(job.found_at).toLocaleDateString() : ''}</span>
            </div>
            {job.reason && (
              <p className="text-slate-400 text-xs mt-1.5 line-clamp-2">{job.reason}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); onTailor(job); }}
            className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded font-medium transition-colors"
          >
            ⚡ Tailor
          </button>
          {job.url && (
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-xs rounded font-medium transition-colors"
            >
              ↗ Open
            </a>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onSkip(job.id); }}
            className="px-3 py-1.5 bg-slate-700 hover:bg-red-900 text-slate-300 hover:text-red-300 text-xs rounded font-medium transition-colors"
          >
            × Skip
          </button>
        </div>
      </div>
    </div>
  )
}

const LIMIT = 20

export default function QueueTab() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [scraping, setScraping] = useState(false)
  const [scrapeStatus, setScrapeStatus] = useState(null)
  const [tailorJob_, setTailorJob] = useState(null)
  const [selectedJob, setSelectedJob] = useState(null)
  const [pendingBatch, setPendingBatch] = useState(null)

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getJobs('new', LIMIT, page * LIMIT)
      setJobs(Array.isArray(data) ? data : data.jobs || [])
      setTotal(data.total || (Array.isArray(data) ? data.length : 0))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [page])

  const fetchScrapeStatus = useCallback(async () => {
    try {
      const s = await getScrapeStatus()
      setScrapeStatus(s)
    } catch (_) {}
  }, [])

  useEffect(() => { fetchJobs() }, [fetchJobs])
  useEffect(() => { fetchScrapeStatus() }, [fetchScrapeStatus])

  // Poll pending batches every 30s and refresh jobs when done
  useEffect(() => {
    let interval
    const checkBatches = async () => {
      try {
        const b = await getBatches()
        if (b.count > 0) {
          setPendingBatch(b.pending[0])
          await pollBatches()
        } else {
          if (pendingBatch) fetchJobs()  // batch just completed, refresh
          setPendingBatch(null)
        }
      } catch (_) {}
    }
    checkBatches()
    interval = setInterval(checkBatches, 30000)
    return () => clearInterval(interval)
  }, [pendingBatch?.batch_id])

  const handleScrape = async () => {
    setScraping(true)
    try {
      await startScrape()
      const poll = setInterval(async () => {
        try {
          const s = await getScrapeStatus()
          setScrapeStatus(s)
          if (s.status !== 'running') {
            clearInterval(poll)
            setScraping(false)
            setPage(0)
            await fetchJobs()
          }
        } catch (_) {
          clearInterval(poll)
          setScraping(false)
        }
      }, 3000)
    } catch (e) {
      setError(e.message)
      setScraping(false)
    }
  }

  const handleSkip = async (id) => {
    try {
      await setJobStatus(id, 'skipped')
      setJobs(prev => prev.filter(j => j.id !== id))
    } catch (e) {
      setError(e.message)
    }
  }

  const handleApply = async (id) => {
    try {
      await setJobStatus(id, 'applied')
      setJobs(prev => prev.filter(j => j.id !== id))
      setSelectedJob(null)
    } catch (e) {
      setError(e.message)
    }
  }

  const totalPages = Math.ceil(total / LIMIT)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-slate-400">
          {scrapeStatus && (
            <span>
              Last run: {scrapeStatus.last_run ? new Date(scrapeStatus.last_run).toLocaleString() : 'never'}
              {scrapeStatus.new_count != null && (
                <span className="ml-3 text-emerald-400">+{scrapeStatus.new_count} new</span>
              )}
            </span>
          )}
        </div>
        <button
          onClick={handleScrape}
          disabled={scraping}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
        >
          {scraping ? '⟳ Scraping...' : '⚡ Scrape Now'}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {pendingBatch && (
        <div className="bg-amber-900/30 border border-amber-700 text-amber-300 px-4 py-3 rounded mb-4 text-sm flex items-center gap-2">
          <span className="animate-spin text-base">⟳</span>
          <span>
            Scoring <strong>{pendingBatch.total_requests.toLocaleString()}</strong> jobs with AI
            <span className="text-amber-400/60 ml-1">(batch mode — 50% cheaper, auto-refreshes)</span>
          </span>
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-500 py-12">Loading jobs...</div>
      ) : jobs.length === 0 ? (
        <div className="text-center text-slate-500 py-12">
          No new jobs in queue. Hit "Scrape Now" to fetch more.
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map(job => (
            <JobCard key={job.id} job={job} onSkip={handleSkip} onTailor={setTailorJob} onClick={() => setSelectedJob(job)} />
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center gap-2 mt-4 justify-center">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 rounded text-sm"
          >
            ← Prev
          </button>
          <span className="text-slate-400 text-sm">Page {page + 1} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 rounded text-sm"
          >
            Next →
          </button>
        </div>
      )}

      {tailorJob_ && (
        <TailorModal job={tailorJob_} onClose={() => setTailorJob(null)} />
      )}

      {selectedJob && (
        <JobDetailModal job={selectedJob} onClose={() => { setSelectedJob(null); fetchJobs(); }} />
      )}
    </div>
  )
}
