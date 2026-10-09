import { useCallback, useEffect, useState } from 'react'
import { Download, RefreshCw, Search } from 'lucide-react'
import { api } from '../api/client'
import { useLiveData } from '../hooks/useLiveData'
import { EventTable } from '../components/EventTable'
import type { EventRecord } from '../types'
import { EmptyState, ErrorBanner, Panel, Spinner } from '../components/ui'

const CATEGORIES = [
  'sensor_reading',
  'sensor_threshold',
  'context_update',
  'agent_proposal',
  'safety_approval',
  'safety_rejection',
  'command_dispatch',
  'device_ack',
  'device_failure',
  'agent_timeout',
  'state_transition',
  'offline_fallback',
  'recovery',
  'manual_override',
  'config_change',
]

const SEVERITIES = ['debug', 'info', 'warning', 'error', 'critical']
const PAGE_SIZE = 25

export default function EventHistory() {
  const { events: liveEvents } = useLiveData()
  const [items, setItems] = useState<EventRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [category, setCategory] = useState('')
  const [severity, setSeverity] = useState('')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const response = await api.events({
        category: category || undefined,
        severity: severity || undefined,
        search: search || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      setItems(response.items)
      setTotal(response.total)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events')
    } finally {
      setLoading(false)
    }
  }, [category, severity, search, page])

  useEffect(() => {
    void load()
  }, [load])

  // Refresh the first page as new events stream in.
  useEffect(() => {
    if (page === 0) void load()
  }, [liveEvents[0]?.event_id, page, load])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="space-y-5">
      <Panel title="Filters">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-slate-400">
            Category
            <select
              className="input mt-1 block"
              value={category}
              onChange={(event) => {
                setPage(0)
                setCategory(event.target.value)
              }}
            >
              <option value="">all</option>
              {CATEGORIES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            Severity
            <select
              className="input mt-1 block"
              value={severity}
              onChange={(event) => {
                setPage(0)
                setSeverity(event.target.value)
              }}
            >
              <option value="">all</option>
              {SEVERITIES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex-1 text-xs text-slate-400">
            Search
            <div className="mt-1 flex gap-2">
              <input
                className="input flex-1"
                placeholder="event type, source, ids…"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    setPage(0)
                    setSearch(searchInput)
                  }
                }}
              />
              <button
                className="btn"
                onClick={() => {
                  setPage(0)
                  setSearch(searchInput)
                }}
              >
                <Search className="h-4 w-4" /> Apply
              </button>
            </div>
          </label>
          <div className="flex gap-2">
            <button className="btn" onClick={() => void load()}>
              <RefreshCw className="h-4 w-4" /> Refresh
            </button>
            <a
              className="btn btn-primary"
              href={api.eventsExportUrl(category || undefined, severity || undefined)}
            >
              <Download className="h-4 w-4" /> Export CSV
            </a>
          </div>
        </div>
      </Panel>

      {error && <ErrorBanner message={error} onRetry={() => void load()} />}

      <Panel
        title={`Events (${total})`}
        bodyClassName="p-0"
        actions={
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <button className="btn" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
              Prev
            </button>
            <span>
              page {page + 1} / {pageCount}
            </span>
            <button
              className="btn"
              disabled={page + 1 >= pageCount}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        }
      >
        {loading ? (
          <div className="p-4">
            <Spinner label="Loading events…" />
          </div>
        ) : items.length === 0 ? (
          <div className="p-4">
            <EmptyState message="No events match the current filters." />
          </div>
        ) : (
          <EventTable events={items} />
        )}
      </Panel>
    </div>
  )
}
