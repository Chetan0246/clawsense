import type { SafetyResult } from '../types'
import { Badge, CheckBadge, EmptyState, formatClock } from './ui'

export function DecisionChecks({ decision }: { decision: SafetyResult | null }) {
  if (!decision) {
    return <EmptyState message="No safety decisions recorded yet." />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={decision.approved ? 'ok' : 'danger'}>
          {decision.approved ? 'APPROVED' : 'REJECTED'}
        </Badge>
        <span className="font-mono text-sm text-slate-300">{decision.reason_code}</span>
        <span className="text-xs text-slate-500">{formatClock(decision.timestamp)}</span>
        {decision.dispatch_attempted && <Badge tone="info">dispatch attempted</Badge>}
      </div>

      <p className="text-sm text-slate-300">{decision.reason}</p>

      <div className="grid grid-cols-1 gap-2 text-xs text-slate-500 sm:grid-cols-2">
        <div>
          decision_id: <span className="font-mono text-slate-400">{decision.decision_id}</span>
        </div>
        <div>
          proposal_id: <span className="font-mono text-slate-400">{decision.proposal_id}</span>
        </div>
      </div>

      <div className="divide-y divide-slate-800 rounded-md border border-slate-800">
        {decision.check_results.map((check) => (
          <div key={check.name} className="flex items-start gap-3 px-3 py-2">
            <div className="w-40 shrink-0">
              <div className="font-mono text-xs text-slate-300">{check.name}</div>
              <div className="text-[10px] text-slate-600">{formatClock(check.timestamp)}</div>
            </div>
            <div className="pt-0.5">
              <CheckBadge status={check.status} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-slate-400">{check.detail}</p>
              {check.code && (
                <p className="mt-0.5 font-mono text-[10px] text-red-400">{check.code}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
