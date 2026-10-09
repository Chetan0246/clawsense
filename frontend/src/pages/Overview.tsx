import { Link } from 'react-router-dom'
import { Activity, ShieldCheck, Cpu, Thermometer, Droplets } from 'lucide-react'
import { useLiveData } from '../hooks/useLiveData'
import { MetricChart } from '../components/MetricChart'
import { EventTable } from '../components/EventTable'
import {
  Badge,
  EmptyState,
  Panel,
  StatCard,
  StaleIndicator,
  StateBadge,
  formatClock,
  formatRelative,
  useNow,
} from '../components/ui'

export default function Overview() {
  const { system, telemetry, history, latestDecision, latestCommand, events } = useLiveData()
  const now = useNow()

  const temp = telemetry?.readings['temperature_c']
  const humidity = telemetry?.readings['humidity_percent']

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="System State"
          value={<StateBadge state={system?.current_state} />}
          hint={system?.transition_reason_code ?? 'no transition yet'}
          icon={<Cpu className="h-4 w-4" />}
        />
        <StatCard
          label="Controller Authority"
          value={system?.controller_authority ?? '—'}
          tone={system?.controller_authority === 'agent' ? 'info' : 'warn'}
          hint={system?.controller_authority === 'local' ? 'deterministic fallback active' : 'AI agent in control'}
          icon={<Activity className="h-4 w-4" />}
        />
        <StatCard
          label="Temperature"
          value={typeof temp?.value === 'number' ? temp.value.toFixed(1) : '—'}
          unit="°C"
          tone={temp?.status === 'OK' ? 'ok' : 'warn'}
          hint={
            <span className="flex items-center gap-2">
              <StaleIndicator ageSeconds={telemetry?.age_seconds} />
            </span>
          }
          icon={<Thermometer className="h-4 w-4" />}
        />
        <StatCard
          label="Humidity"
          value={typeof humidity?.value === 'number' ? humidity.value.toFixed(1) : '—'}
          unit="%"
          tone={humidity?.status === 'OK' ? 'ok' : 'warn'}
          hint={humidity?.status ?? 'no data'}
          icon={<Droplets className="h-4 w-4" />}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <Panel
          title="Latest Safety Decision"
          className="xl:col-span-2"
          actions={
            <Link to="/safety" className="text-xs text-sky-400 hover:text-sky-300">
              Open Safety Center →
            </Link>
          }
        >
          {latestDecision ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <Badge tone={latestDecision.approved ? 'ok' : 'danger'}>
                  {latestDecision.approved ? 'APPROVED' : 'REJECTED'}
                </Badge>
                <span className="font-mono text-sm text-slate-200">{latestDecision.reason_code}</span>
                <span className="text-xs text-slate-500">{formatRelative(latestDecision.timestamp, now)}</span>
              </div>
              <p className="text-sm text-slate-300">{latestDecision.reason}</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(latestDecision.checks).map(([name, status]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between rounded border border-slate-800 px-2 py-1"
                  >
                    <span className="font-mono text-[10px] text-slate-500">{name}</span>
                    <span
                      className={`text-[10px] font-bold ${
                        status === 'PASS'
                          ? 'text-emerald-400'
                          : status === 'FAIL'
                            ? 'text-red-400'
                            : 'text-slate-500'
                      }`}
                    >
                      {status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState message="No safety decision recorded yet." />
          )}
        </Panel>

        <Panel title="Latest Command">
          {latestCommand ? (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Action</span>
                <span className="font-mono text-slate-200">{latestCommand.action}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Status</span>
                <Badge
                  tone={
                    latestCommand.status.includes('CONFIRMED') || latestCommand.status === 'ACKNOWLEDGED'
                      ? 'ok'
                      : latestCommand.status === 'FAILED' || latestCommand.status === 'TIMEOUT'
                        ? 'danger'
                        : 'warn'
                  }
                >
                  {latestCommand.status}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Target</span>
                <span className="font-mono text-xs text-slate-300">{latestCommand.target_device}</span>
              </div>
              <div>
                <div className="text-slate-400">Parameters</div>
                <code className="mt-1 block rounded bg-slate-950 p-2 font-mono text-xs text-slate-300">
                  {JSON.stringify(latestCommand.parameters)}
                </code>
              </div>
              <div className="text-xs text-slate-500">
                created {formatClock(latestCommand.created_at)}
                {latestCommand.acknowledged_at && ` · acked ${formatClock(latestCommand.acknowledged_at)}`}
              </div>
              {latestCommand.error && (
                <div className="rounded border border-red-900 bg-red-950/40 px-2 py-1 text-xs text-red-300">
                  {latestCommand.error}
                </div>
              )}
            </div>
          ) : (
            <EmptyState message="No commands dispatched yet." />
          )}
        </Panel>
      </div>

      <Panel title="Temperature Trend" bodyClassName="p-2">
        <MetricChart
          data={history}
          dataKey="temperature_c"
          label="Temperature"
          unit="°C"
          color="#f97316"
          height={220}
        />
      </Panel>

      <Panel
        title="Recent Events"
        actions={
          <Link to="/events" className="text-xs text-sky-400 hover:text-sky-300">
            View all →
          </Link>
        }
        bodyClassName="p-0"
      >
        <EventTable events={events.slice(0, 8)} compact />
      </Panel>

      <div className="flex items-center gap-2 text-xs text-slate-600">
        <ShieldCheck className="h-3.5 w-3.5" />
        Every actuator command is validated by the deterministic safety supervisor before
        dispatch. An approval is not proof of physical safety — the device re-validates
        independently.
      </div>
    </div>
  )
}
