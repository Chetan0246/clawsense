import { useCallback, useEffect, useState } from 'react'
import { FlaskConical, ShieldAlert, ShieldCheck } from 'lucide-react'
import { api } from '../api/client'
import { useLiveData } from '../hooks/useLiveData'
import { DecisionChecks } from '../components/DecisionChecks'
import type { SafetyResult, SafetyTestReport } from '../types'
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

const ACTIONS = ['servo_move', 'buzzer_beep', 'set_status_led', 'no_op'] as const
type ActionName = (typeof ACTIONS)[number]

export default function SafetyCenter() {
  const { latestDecision } = useLiveData()
  const now = useNow()
  const [decisions, setDecisions] = useState<SafetyResult[]>([])
  const [selected, setSelected] = useState<SafetyResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Dry-run form
  const [action, setAction] = useState<ActionName>('servo_move')
  const [angle, setAngle] = useState(90)
  const [duration, setDuration] = useState(500)
  const [color, setColor] = useState('green')
  const [source, setSource] = useState('agent')
  const [dryRun, setDryRun] = useState<SafetyResult | null>(null)
  const [dryRunError, setDryRunError] = useState<string | null>(null)
  const [dryRunBusy, setDryRunBusy] = useState(false)

  const [testReport, setTestReport] = useState<SafetyTestReport | null>(null)
  const [testBusy, setTestBusy] = useState(false)
  const [testError, setTestError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const response = await api.safetyDecisions(60)
      setDecisions(response.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load decisions')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    void load()
  }, [latestDecision?.decision_id, load])

  const parameters = (): Record<string, unknown> => {
    switch (action) {
      case 'servo_move':
        return { angle_degrees: angle }
      case 'buzzer_beep':
        return { duration_ms: duration }
      case 'set_status_led':
        return { color }
      default:
        return {}
    }
  }

  const runDryRun = async () => {
    setDryRunBusy(true)
    setDryRunError(null)
    try {
      const result = await api.safetyValidate({
        proposal_id: `dry-run-${Date.now()}`,
        action,
        parameters: parameters(),
        source,
        reason: 'Safety Center dry run',
      })
      setDryRun(result)
    } catch (err) {
      setDryRunError(err instanceof Error ? err.message : 'Validation failed')
    } finally {
      setDryRunBusy(false)
    }
  }

  const runTests = async () => {
    setTestBusy(true)
    setTestError(null)
    try {
      setTestReport(await api.safetyTest())
    } catch (err) {
      setTestError(err instanceof Error ? err.message : 'Safety test run failed')
    } finally {
      setTestBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <Panel title="How validation works">
        <div className="grid grid-cols-1 gap-3 text-sm text-slate-400 sm:grid-cols-2">
          <p>
            The deterministic safety supervisor runs eight independent checks — schema, allow-list,
            parameter types, numeric range, context freshness, system state, cooldown, and duplicate
            detection — and reports each one separately.
          </p>
          <p>
            The supervisor has <span className="text-slate-200">no dependency on the LLM</span>. A
            software approval is not proof of physical safety: the ESP32 re-validates every command
            independently before driving an actuator.
          </p>
        </div>
      </Panel>

      <Panel
        title="Predefined Safety Tests"
        actions={
          <div className="flex items-center gap-2">
            {testReport && (
              <Badge tone={testReport.passed === testReport.total ? 'ok' : 'danger'}>
                {testReport.passed}/{testReport.total} passed
              </Badge>
            )}
            <button className="btn btn-primary" onClick={() => void runTests()} disabled={testBusy}>
              <FlaskConical className="h-4 w-4" /> Run Safety Test
            </button>
          </div>
        }
      >
        <p className="mb-3 text-xs text-slate-500">
          These call the <span className="text-slate-300">actual backend safety supervisor</span> —
          the same code path used for live proposals. They are{' '}
          <span className="text-amber-300">software validation tests</span>, not a hardware test.
        </p>
        {testError && <ErrorBanner message={testError} onRetry={() => void runTests()} />}
        {testBusy && <Spinner label="Running safety tests…" />}
        {testReport && (
          <div className="space-y-2">
            {testReport.results.map((item) => (
              <div
                key={item.key}
                className="flex flex-wrap items-start gap-3 rounded border border-slate-800 px-3 py-2"
              >
                <Badge tone={item.passed ? 'ok' : 'danger'}>{item.passed ? 'PASS' : 'FAIL'}</Badge>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-slate-200">{item.name}</div>
                  <div className="text-xs text-slate-500">{item.description}</div>
                  <code className="mt-1 block font-mono text-[11px] text-slate-500">
                    {JSON.stringify(item.payload)}
                  </code>
                </div>
                <div className="text-right text-xs">
                  <div className="text-slate-500">
                    expected{' '}
                    <span className="text-slate-300">
                      {item.expected.approved ? 'APPROVED' : 'REJECTED'}
                    </span>
                  </div>
                  <div className="text-slate-500">
                    got{' '}
                    <span
                      className={
                        item.result.approved ? 'text-emerald-400' : 'text-red-400'
                      }
                    >
                      {item.result.approved ? 'APPROVED' : 'REJECTED'}
                    </span>
                  </div>
                  <div className="font-mono text-[10px] text-slate-500">
                    {item.result.reason_code}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel
          title="Latest Decision"
          actions={
            <Badge tone={latestDecision?.approved ? 'ok' : 'danger'}>
              {latestDecision ? (latestDecision.approved ? 'APPROVED' : 'REJECTED') : 'none'}
            </Badge>
          }
        >
          <DecisionChecks decision={latestDecision} />
        </Panel>

        <Panel title="Dry-Run Validation (no dispatch)">
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-slate-400">
                Action
                <select
                  className="input mt-1 w-full"
                  value={action}
                  onChange={(event) => setAction(event.target.value as ActionName)}
                >
                  {ACTIONS.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-slate-400">
                Source
                <select
                  className="input mt-1 w-full"
                  value={source}
                  onChange={(event) => setSource(event.target.value)}
                >
                  <option value="agent">agent</option>
                  <option value="fallback">fallback</option>
                  <option value="operator">operator</option>
                </select>
              </label>
            </div>

            {action === 'servo_move' && (
              <label className="block text-xs text-slate-400">
                Angle (degrees)
                <input
                  type="number"
                  className="input mt-1 w-full"
                  value={angle}
                  onChange={(event) => setAngle(Number(event.target.value))}
                />
              </label>
            )}
            {action === 'buzzer_beep' && (
              <label className="block text-xs text-slate-400">
                Duration (ms)
                <input
                  type="number"
                  className="input mt-1 w-full"
                  value={duration}
                  onChange={(event) => setDuration(Number(event.target.value))}
                />
              </label>
            )}
            {action === 'set_status_led' && (
              <label className="block text-xs text-slate-400">
                Color
                <select
                  className="input mt-1 w-full"
                  value={color}
                  onChange={(event) => setColor(event.target.value)}
                >
                  <option value="green">green</option>
                  <option value="yellow">yellow</option>
                  <option value="red">red</option>
                  <option value="off">off</option>
                </select>
              </label>
            )}

            <div className="flex items-center gap-2">
              <button className="btn btn-primary" onClick={() => void runDryRun()} disabled={dryRunBusy}>
                <ShieldCheck className="h-4 w-4" /> Validate
              </button>
              <span className="text-xs text-slate-500">
                Nothing is dispatched — this only exercises the supervisor.
              </span>
            </div>

            {dryRunError && <ErrorBanner message={dryRunError} />}
            {dryRunBusy && <Spinner label="Validating…" />}
            {dryRun && (
              <div className="mt-2 rounded-md border border-slate-800 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs text-slate-400">
                  <ShieldAlert className="h-3.5 w-3.5" /> dry-run result
                </div>
                <DecisionChecks decision={dryRun} />
              </div>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Decision History" bodyClassName="p-0">
        {loading && (
          <div className="p-4">
            <Spinner label="Loading decisions…" />
          </div>
        )}
        {error && (
          <div className="p-4">
            <ErrorBanner message={error} onRetry={() => void load()} />
          </div>
        )}
        {!loading && decisions.length === 0 && (
          <div className="p-4">
            <EmptyState message="No decisions recorded yet." />
          </div>
        )}
        {decisions.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Result</th>
                  <th className="px-3 py-2">Reason</th>
                  <th className="px-3 py-2">Proposal</th>
                  <th className="px-3 py-2">Checks</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {decisions.map((decision) => (
                  <tr key={decision.decision_id} className="table-row-hover align-top">
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-400">
                      {formatClock(decision.timestamp)}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={decision.approved ? 'ok' : 'danger'}>
                        {decision.approved ? 'APPROVED' : 'REJECTED'}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-300">{decision.reason_code}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-500">
                      {decision.proposal_id.slice(0, 8)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(decision.checks)
                          .filter(([, status]) => status !== 'PASS')
                          .map(([name, status]) => (
                            <span
                              key={name}
                              className={`rounded px-1 py-0.5 font-mono text-[10px] ${
                                status === 'FAIL'
                                  ? 'bg-red-950/60 text-red-400'
                                  : 'bg-slate-800 text-slate-500'
                              }`}
                            >
                              {name}:{status}
                            </span>
                          ))}
                        {Object.values(decision.checks).every((status) => status === 'PASS') && (
                          <span className="text-[10px] text-emerald-500">all pass</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button className="text-xs text-sky-400 hover:text-sky-300" onClick={() => setSelected(decision)}>
                        inspect
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {selected && (
        <Panel
          title={`Decision ${selected.decision_id.slice(0, 8)}`}
          actions={
            <button className="btn" onClick={() => setSelected(null)}>
              Close
            </button>
          }
        >
          <DecisionChecks decision={selected} />
          <p className="mt-2 text-xs text-slate-500">
            recorded {formatRelative(selected.timestamp, now)}
          </p>
        </Panel>
      )}
    </div>
  )
}
