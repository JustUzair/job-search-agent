import { useState, useEffect, useCallback } from 'react'
import { getAllJobs, getSources } from '../api.js'
import { WorkTypeBadge } from './QueueTab.jsx'
import JobDetailModal from './JobDetailModal.jsx'

const SCORE_TEXT = (score) => {
  if (score >= 75) return 'text-emerald-400'
  if (score >= 55) return 'text-amber-400'
  return 'text-red-400'
}

const STATUSES = ['', 'new', 'applied', 'skipped', 'tailored', 'filtered']
const LIMIT = 50

export default function AllResultsTab() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [source, setSource] = useState('')
  const [status, setStatus] = useState('')
  const [selectedJob, setSelectedJob] = useState(null)
  const [sources, setSources] = useState([])

  useEffect(() => {
    getSources().then(s => setSources(s || [])).catch(() => {})
  }, [])

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getAllJobs(LIMIT, page * LIMIT, source, status)
      setJobs(Array.isArray(data) ? data : data.jobs || [])
      setTotal(data.total || (Array.isArray(data) ? data.length : 0))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, source, status])

  useEffect(() => { fetchJobs() }, [fetchJobs])

  const handleFilterChange = (setter) => (e) => {
    setter(e.target.value)
    setPage(0)
  }

  const totalPages = Math.ceil(total / LIMIT)
  const selectCls = 'bg-slate-700 border border-slate-600 text-white text-sm rounded px-3 py-1.5 focus:outline-none focus:border-emerald-500'

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <select value={source} onChange={handleFilterChange(setSource)} className={selectCls}>
          <option value="">All Sources</option>
          {sources.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={status} onChange={handleFilterChange(setStatus)} className={selectCls}>
          {STATUSES.map(s => <option key={s} value={s}>{s || 'All Statuses'}</option>)}
        </select>
        <span className="text-slate-500 text-sm ml-auto">{total} jobs</span>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-500 py-12">Loading...</div>
      ) : jobs.length === 0 ? (
        <div className="text-center text-slate-500 py-12">No jobs found.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-700">
                <th className="pb-2 pr-4">Score</th>
                <th className="pb-2 pr-4">Company</th>
                <th className="pb-2 pr-4">Title</th>
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4">Type</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2">Found</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr
                  key={job.id}
                  onClick={() => setSelectedJob(job)}
                  className="border-b border-slate-800 hover:bg-slate-800/60 cursor-pointer transition-colors"
                >
                  <td className="py-2 pr-4">
                    <span className={`font-bold ${SCORE_TEXT(job.score)}`}>{job.score ?? '?'}</span>
                  </td>
                  <td className="py-2 pr-4 text-slate-300 truncate max-w-[140px]">{job.company}</td>
                  <td className="py-2 pr-4 text-white truncate max-w-[200px]">{job.title}</td>
                  <td className="py-2 pr-4 text-slate-400">{job.source}</td>
                  <td className="py-2 pr-4"><WorkTypeBadge type={job.work_type} /></td>
                  <td className="py-2 pr-4">
                    <span className="text-xs text-slate-400 bg-slate-700 px-2 py-0.5 rounded-full">{job.status}</span>
                  </td>
                  <td className="py-2 text-slate-500 text-xs">
                    {job.found_at ? new Date(job.found_at).toLocaleDateString() : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

      {selectedJob && (
        <JobDetailModal job={selectedJob} onClose={() => setSelectedJob(null)} />
      )}
    </div>
  )
}
