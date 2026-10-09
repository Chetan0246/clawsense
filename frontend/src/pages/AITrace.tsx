import { useCallback, useEffect, useState } from 'react'
import { ArrowRight, BrainCircuit, CheckCircle2, Cpu, XCircle } from 'lucide-react'
import { api } from '../api/client'
import { useLiveData } from '../hooks/useLiveData'
import type { ActionProposal, CommandRecord, EventRecord, SafetyResult } from '../types'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Panel,
  Spinner,
  formatClock,
  formatRelative,
  useNow,
} from '../components/ui'

interface Trace {
  proposal: ActionProposal
  decision: SafetyResult | null
  command: CommandRecord | null
  events: EventRecord[]
}

function reportedState(events: EventRecord[]): Record<string, unknown> | null {
  const ack = events.find((event) => event.event_type === 'COMMAND_ACKNOWLEDGED')
  const state = ack?.details?.reported_state
  return state && typeof state === 'object' ? (state as Record<string, unknown>) : null
}

export default function AITrace() {
  const { latestDecision, latestCommand } = useLiveData()
  const now = useNow()
  const [traces, setTraces] = useState<Trace[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [proposals, decisions, commands, events] = await Promise.all([
        api.proposals(60),
        api.safetyDecisions(60),
        api.commands(60),
        api.events({ limit: 300 }),
      ])
      const decisionByProposal = new Map(decisions.items.map((d) => [d.proposal_id, d]))
      const commandByProposal = new Map(commands.items.map((c) => [c.proposal_id, c]))
      const eventsByProposal = new Map<string, EventRecord[]>()
      for (const event of events.items) {
        if (!event.proposal_id) continue
        const list = eventsByProposal.get(event.proposal_id) ?? []
        list.push(event)
        eventsByProposal.set(event.proposal_id, list)
      }
      const merged: Trace[] = proposals.items.map((proposal) => ({
        proposal,
        decision: decisionByProposal.get(proposal.proposal_id) ?? null,
        command: commandByProposal.get(proposal.proposal_id) ?? null,
        events: eventsByProposal.get(proposal.proposal_id) ?? [],
      }))
      setTraces(merged)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trace')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // Reload when a new decision or command arrives over the WebSocket.
  useEffect(() => {
    void load()
  }, [latestDecision?.decision_id, latestCommand?.command_id, load])

  return (
    <div className="space-y-5">
      <Panel
        title="Agent → Supervisor → Device Trace"
        actions={
          <button className="btn" onClick={() => void load()}>
            Refresh
          </button>
        }
      >
        <p className="text-sm text-slate-400">
          Every AI proposal is recorded, then validated by the deterministic safety supervisor, then
          (only if approved) dispatched to the device. This view correlates all three stages.
        </p>
      </Panel>

      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {loading && <Spinner label="Loading trace…" />}
      {!loading && traces.length === 0 && <EmptyState message="No proposals recorded yet." />}

      <div className="space-y-3">
        {traces.map(({ proposal, decision, command, events }) => {
          const reported = reportedState(events)
          return (
          <div key={proposal.proposal_id} className="panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge tone={proposal.source === 'fallback' ? 'warn' : 'info'}>
                  {proposal.source === 'fallback' ? 'LOCAL FALLBACK' : proposal.source.toUpperCase()}
                </Badge>
                <span className="font-mono text-sm text-slate-100">{proposal.action}</span>
                <code className="rounded bg-slate-950 px-1.5 py-0.5 font-mono text-xs text-slate-400">
                  {JSON.stringify(proposal.parameters)}
                </code>
              </div>
              <span className="text-xs text-slate-500">{formatRelative(proposal.created_at, now)}</span>
            </div>

            {proposal.reason && (
              <p className="mt-2 text-xs italic text-slate-400">“{proposal.reason}”</p>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="flex items-center gap-1 rounded border border-slate-800 px-2 py-1 text-slate-400">
                <BrainCircuit className="h-3.5 w-3.5" /> proposal
                <span className="font-mono text-slate-600">{proposal.proposal_id.slice(0, 8)}</span>
              </span>
              <ArrowRight className="h-3.5 w-3.5 text-slate-600" />
              {decision ? (
                <span
                  className={`flex items-center gap-1 rounded border px-2 py-1 ${
                    decision.approved
                      ? 'border-emerald-800 bg-emerald-950/40 text-emerald-300'
                      : 'border-red-800 bg-red-950/40 text-red-300'
                  }`}
                >
                  {decision.approved ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5" />
                  )}
                  {decision.approved ? 'approved' : 'rejected'} · {decision.reason_code}
                </span>
              ) : (
                <span className="rounded border border-slate-800 px-2 py-1 text-slate-500">
                  no decision
                </span>
              )}
              <ArrowRight className="h-3.5 w-3.5 text-slate-600" />
              {command ? (
                <span className="flex items-center gap-1 rounded border border-slate-700 px-2 py-1 text-slate-300">
                  <Cpu className="h-3.5 w-3.5" /> {command.status}
                  {command.error && <span className="text-red-400">· {command.error}</span>}
                </span>
              ) : (
                <span className="rounded border border-slate-800 px-2 py-1 text-slate-500">
                  not dispatched
                </span>
              )}
            </div>

            {decision && (
              <div className="mt-2 flex flex-wrap gap-1">
                {Object.entries(decision.checks).map(([name, status]) => (
                  <span
                    key={name}
                    className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                      status === 'PASS'
                        ? 'bg-emerald-950/50 text-emerald-400'
                        : status === 'FAIL'
                          ? 'bg-red-950/50 text-red-400'
                          : 'bg-slate-800 text-slate-500'
                    }`}
                  >
                    {name}:{status}
                  </span>
                ))}
                <span className="px-1.5 py-0.5 text-[10px] text-slate-600">
                  decided {formatClock(decision.timestamp)}
                </span>
              </div>
            )}

            {reported && (
              <div className="mt-2 rounded border border-emerald-900/60 bg-emerald-950/20 px-2 py-1 text-[11px] text-emerald-300">
                device-reported state:{' '}
                <span className="font-mono">{JSON.stringify(reported)}</span>
              </div>
            )}

            {events.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[11px] text-slate-500 hover:text-slate-400">
                  {events.length} related event(s)
                </summary>
                <ul className="mt-1 space-y-0.5">
                  {events.map((event) => (
                    <li
                      key={event.event_id}
                      className="flex items-center gap-2 font-mono text-[10px] text-slate-500"
                    >
                      <span>{formatClock(event.timestamp)}</span>
                      <span className="text-slate-400">{event.event_type}</span>
                      <span className="truncate text-slate-600">
                        {JSON.stringify(event.details)}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
          )
        })}
      </div>
    </div>
  )
}
