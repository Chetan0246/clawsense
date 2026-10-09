import { useLiveData } from '../hooks/useLiveData'
import { MetricChart } from '../components/MetricChart'
import { SensorCard } from '../components/SensorCard'
import { Badge, EmptyState, Panel, StaleIndicator } from '../components/ui'

export default function LiveSensors() {
  const { telemetry, history, simulated } = useLiveData()

  const readings = telemetry ? Object.values(telemetry.readings) : []
  const ordered = ['temperature_c', 'humidity_percent', 'motion', 'light_lux']
    .map((key) => readings.find((reading) => reading.sensor === key))
    .filter((reading): reading is NonNullable<typeof reading> => Boolean(reading))
  const extras = readings.filter((reading) => !ordered.includes(reading))

  return (
    <div className="space-y-5">
      <Panel
        title="Sensor Snapshot"
        actions={
          <div className="flex items-center gap-2">
            {simulated && <Badge tone="warn">SIMULATED DATA</Badge>}
            <StaleIndicator ageSeconds={telemetry?.age_seconds} />
          </div>
        }
      >
        {ordered.length === 0 && extras.length === 0 ? (
          <EmptyState message="Waiting for the first telemetry snapshot…" />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[...ordered, ...extras].map((reading) => (
              <SensorCard key={reading.sensor} reading={reading} />
            ))}
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel title="Temperature" bodyClassName="p-2">
          <MetricChart
            data={history}
            dataKey="temperature_c"
            label="Temperature"
            unit="°C"
            color="#f97316"
            height={240}
          />
        </Panel>
        <Panel title="Humidity" bodyClassName="p-2">
          <MetricChart
            data={history}
            dataKey="humidity_percent"
            label="Humidity"
            unit="%"
            color="#38bdf8"
            domain={[0, 100]}
            height={240}
          />
        </Panel>
      </div>

      <Panel title="Ambient Light" bodyClassName="p-2">
        <MetricChart
          data={history}
          dataKey="light_lux"
          label="Light"
          unit="lux"
          color="#facc15"
          height={200}
        />
      </Panel>

      <Panel title="Data Quality">
        <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
          <div className="rounded border border-slate-800 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Origin</div>
            <div className="mt-1">
              {simulated ? (
                <Badge tone="warn">Simulated device</Badge>
              ) : (
                <Badge tone="ok">Hardware device</Badge>
              )}
            </div>
          </div>
          <div className="rounded border border-slate-800 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Device</div>
            <div className="mt-1 font-mono text-xs text-slate-300">
              {telemetry?.device_id ?? '—'}
            </div>
          </div>
          <div className="rounded border border-slate-800 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Context age</div>
            <div className="mt-1">
              <StaleIndicator ageSeconds={telemetry?.age_seconds} />
            </div>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Sensor readings that are missing, stale, or in error are never coerced to zero; they are
          surfaced as-is so the supervisor can fail closed.
        </p>
      </Panel>
    </div>
  )
}
