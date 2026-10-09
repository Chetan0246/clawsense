import { useCallback, useEffect, useState } from 'react'
import { Lock, RotateCcw, AlertTriangle } from 'lucide-react'
import { api } from '../api/client'
import { useLiveData } from '../hooks/useLiveData'
import type { SimulationState, StateTransition, SystemStateName } from '../types'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Panel,
  Spinner,
  StateBadge,
  formatClock,
  formatRelative,
  useNow,
} from '../components/ui'

const STATES: SystemStateName[] = [
  'ONLINE_AGENT',
  'DEGRADED',
  'OFFLINE_LOCAL',
  'RECOVERY',
  'SAFE_LOCKDOWN',
]

const SCENARIOS = ['normal', 'heatwave', 'cold', 'motion', 'high_humidity', 'sensor_fault', 'stale']
const AGENT_MODES = ['auto', 'unsafe_angle', 'led_alert', 'noop']
const FAILURE_MODES = ['none', 'timeout', 'reject', 'uncertain']

function HealthRow({
  label,
  ok,
  detail,
}: {
  label: string
  ok: boolean
  detail?: string
}) {
  return (
    <div className="flex items-center justify-between rounded border border-slate-800 px-3 py-2">
      <span className="text-sm text-slate-400">{label}</span>
      <div className="flex items-center gap-2">
        {detail && <span className="text-xs text-slate-500">{detail}</span>}
        <Badge tone={ok ? 'ok' : 'danger'}>{ok ? 'OK' : 'FAIL'}</Badge>
      </div>
    </div>
  )
}

export default function SystemHealth() {
  const { system, refresh } = useLiveData()
  const now = useNow()
  const [transitions, setTransitions] = useState<StateTransition[]>([])
  const [sim, setSim] = useState<SimulationState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const [transitionResponse, simulationState] = await Promise.all([
        api.transitions(40),
        api.simulationState(),
      ])
      setTransitions(transitionResponse.items)
      setSim(simulationState)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load system health')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    void load()
  }, [system?.current_state, load])

  const guard = async (operation: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await operation()
      await load()
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Operation failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}

      <Panel title="State Machine">
        <div className="flex flex-wrap items-center gap-2">
          {STATES.map((state, index) => (
            <div key={state} className="flex items-center gap-2">
              <div
                className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                  system?.current_state === state
                    ? 'border-sky-500 bg-sky-600/20 text-sky-200'
                    : 'border-slate-800 text-slate-500'
                }`}
              >
                {state.replace('_', ' ')}
              </div>
              {index < STATES.length - 1 && <span className="text-slate-700">→</span>}
            </div>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-slate-500 sm:grid-cols-2">
          <div>
            Previous state:{' '}
            <span className="font-mono text-slate-400">
              {system?.previous_state ?? '—'}
            </span>
          </div>
          <div>
            Last transition:{' '}
            <span className="font-mono text-slate-400">
              {system?.transition_reason_code ?? '—'}
            </span>{' '}
            {system?.last_transition_at && `(${formatRelative(system.last_transition_at, now)})`}
          </div>
        </div>
        {system?.transition_reason && (
          <p className="mt-2 text-xs italic text-slate-500">{system.transition_reason}</p>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel title="Health Signals">
          <div className="space-y-2">
            <HealthRow
              label="Agent available"
              ok={Boolean(system?.agent_available)}
              detail={system?.agent_provider}
            />
            <HealthRow label="Network available" ok={Boolean(system?.network_available)} />
            <HealthRow label="Device connected" ok={Boolean(system?.device_connected)} />
            <div className="flex items-center justify-between rounded border border-slate-800 px-3 py-2 text-sm">
              <span className="text-slate-400">Recovery status</span>
              <Badge tone={system?.recovery_status === 'complete' ? 'ok' : 'neutral'}>
                {system?.recovery_status ?? 'idle'}
              </Badge>
            </div>
            <div className="flex items-center justify-between rounded border border-slate-800 px-3 py-2 text-sm">
              <span className="text-slate-400">Last agent contact</span>
              <span className="text-xs text-slate-400">
                {formatRelative(system?.last_successful_agent_request, now)}
              </span>
            </div>
            <div className="flex items-center justify-between rounded border border-slate-800 px-3 py-2 text-sm">
              <span className="text-slate-400">Last device contact</span>
              <span className="text-xs text-slate-400">
                {formatRelative(system?.last_successful_device_communication, now)}
              </span>
            </div>
            <div className="flex items-center justify-between rounded border border-slate-800 px-3 py-2 text-sm">
              <span className="text-slate-400">Uptime</span>
              <span className="font-mono text-xs text-slate-400">
                {system ? `${Math.floor(system.uptime_seconds)}s` : '—'}
              </span>
            </div>
          </div>
        </Panel>

        <Panel title="Safety Controls">
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-danger"
                disabled={busy}
                onClick={() => void guard(() => api.lockdown())}
              >
                <Lock className="h-4 w-4" /> Trigger Safe Lockdown
              </button>
              <button className="btn" disabled={busy} onClick={() => void guard(() => api.reset())}>
                <RotateCcw className="h-4 w-4" /> Clear Fault (→ Recovery)
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Lockdown rejects all actuator commands and is only exited via an explicit operator
              reset, which enters RECOVERY for health re-validation.
            </p>
            <div className="flex items-start gap-2 rounded border border-amber-900 bg-amber-950/30 p-2 text-xs text-amber-300">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Manual overrides are recorded in the audit log with a MANUAL_OVERRIDE reason code.
            </div>
          </div>
        </Panel>
      </div>

      {sim?.simulated && (
        <Panel title="Simulation Controls">
          {loading && <Spinner label="Loading…" />}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div>
              <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">Scenario</div>
              <div className="flex flex-wrap gap-2">
                {SCENARIOS.map((scenario) => (
                  <button
                    key={scenario}
                    className={`btn ${sim.device?.scenario === scenario ? 'btn-primary' : ''}`}
                    disabled={busy}
                    onClick={() => void guard(() => api.setScenario(scenario))}
                  >
                    {scenario}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">Agent Mode</div>
              <div className="flex flex-wrap gap-2">
                {AGENT_MODES.map((mode) => (
                  <button
                    key={mode}
                    className={`btn ${sim.agent_mode === mode ? 'btn-primary' : ''}`}
                    disabled={busy}
                    onClick={() => void guard(() => api.setAgentMode(mode))}
                  >
                    {mode}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-slate-600">
                “unsafe_angle” makes the simulated agent propose an out-of-range angle to demonstrate
                deterministic rejection.
              </p>
            </div>
            <div>
              <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">
                Device Failure Injection
              </div>
              <div className="flex flex-wrap gap-2">
                {FAILURE_MODES.map((mode) => (
                  <button
                    key={mode}
                    className={`btn ${sim.transport_failure_mode === mode ? 'btn-primary' : ''}`}
                    disabled={busy}
                    onClick={() => void guard(() => api.setFailureMode(mode))}
                  >
                    {mode}
                  </button>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => void guard(() => api.setAgentAvailability(false))}
                >
                  Force agent offline
                </button>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => void guard(() => api.setAgentAvailability(true))}
                >
                  Restore agent
                </button>
              </div>
            </div>
          </div>
          {sim.device && (
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-slate-500 sm:grid-cols-4">
              <div>
                servo: <span className="font-mono text-slate-300">{sim.device.servo_angle}°</span>
              </div>
              <div>
                LED: <span className="font-mono text-slate-300">{sim.device.led_color}</span>
              </div>
              <div>
                buzzer:{' '}
                <span className="font-mono text-slate-300">
                  {sim.device.buzzer_active ? `${sim.device.buzzer_duration_ms}ms` : 'idle'}
                </span>
              </div>
              <div>
                firmware: <span className="font-mono text-slate-300">{sim.device.firmware_version}</span>
              </div>
            </div>
          )}
        </Panel>
      )}

      <Panel title="Transition History" bodyClassName="p-0">
        {loading ? (
          <div className="p-4">
            <Spinner label="Loading transitions…" />
          </div>
        ) : transitions.length === 0 ? (
          <div className="p-4">
            <EmptyState message="No state transitions recorded yet." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">From</th>
                  <th className="px-3 py-2">To</th>
                  <th className="px-3 py-2">Reason code</th>
                  <th className="px-3 py-2">Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {transitions.map((transition) => (
                  <tr key={transition.transition_id} className="table-row-hover">
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-400">
                      {formatClock(transition.timestamp)}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-400">
                      {transition.previous_state ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      <StateBadge state={transition.new_state} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-300">
                      {transition.reason_code}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-400">{transition.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
