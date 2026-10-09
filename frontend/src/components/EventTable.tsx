import type { EventRecord } from '../types'
import { Badge, EmptyState, formatClock, severityTone } from './ui'

export function EventTable({
  events,
  compact = false,
}: {
  events: EventRecord[]
  compact?: boolean
}) {
  if (events.length === 0) {
    return <EmptyState message="No events match the current filters." />
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Time</th>
            <th className="px-3 py-2">Severity</th>
            <th className="px-3 py-2">Event</th>
            <th className="px-3 py-2">Category</th>
            {!compact && <th className="px-3 py-2">Source</th>}
            {!compact && <th className="px-3 py-2">Details</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/70">
          {events.map((event) => (
            <tr key={event.event_id} className="table-row-hover align-top">
              <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-400">
                {formatClock(event.timestamp)}
              </td>
              <td className="px-3 py-2">
                <Badge tone={severityTone(event.severity)}>{event.severity}</Badge>
              </td>
              <td className="px-3 py-2 font-mono text-xs text-slate-200">{event.event_type}</td>
              <td className="px-3 py-2 text-xs text-slate-400">{event.category}</td>
              {!compact && <td className="px-3 py-2 text-xs text-slate-400">{event.source}</td>}
              {!compact && (
                <td className="max-w-md px-3 py-2">
                  <code className="block truncate font-mono text-[11px] text-slate-500">
                    {JSON.stringify(event.details)}
                  </code>
                  {(event.proposal_id || event.command_id) && (
                    <div className="mt-0.5 flex gap-2 font-mono text-[10px] text-slate-600">
                      {event.proposal_id && <span>p:{event.proposal_id.slice(0, 8)}</span>}
                      {event.command_id && <span>c:{event.command_id.slice(0, 8)}</span>}
                    </div>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
