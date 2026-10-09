import type { SensorReading } from '../types'
import { Badge, formatRelative, useNow } from './ui'

const SENSOR_META: Record<string, { label: string; unit: string; precision: number }> = {
  temperature_c: { label: 'Temperature', unit: '°C', precision: 1 },
  humidity_percent: { label: 'Humidity', unit: '%', precision: 1 },
  motion: { label: 'Motion (PIR)', unit: '', precision: 0 },
  light_lux: { label: 'Light', unit: 'lux', precision: 0 },
}

function statusTone(status: SensorReading['status']): 'ok' | 'warn' | 'danger' | 'neutral' {
  switch (status) {
    case 'OK':
      return 'ok'
    case 'STALE':
      return 'warn'
    case 'ERROR':
    case 'UNAVAILABLE':
      return 'danger'
    default:
      return 'neutral'
  }
}

export function SensorCard({ reading }: { reading: SensorReading }) {
  const now = useNow()
  const meta = SENSOR_META[reading.sensor] ?? {
    label: reading.sensor,
    unit: reading.unit,
    precision: 1,
  }

  let display: string
  if (reading.value === null || reading.value === undefined) {
    display = '—'
  } else if (typeof reading.value === 'boolean') {
    display = reading.value ? 'DETECTED' : 'clear'
  } else if (typeof reading.value === 'number') {
    display = reading.value.toFixed(meta.precision)
  } else {
    display = String(reading.value)
  }

  const stale = reading.status !== 'OK' || reading.value === null

  return (
    <div className="panel p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">{meta.label}</div>
          <div className="mt-1 font-mono text-xs text-slate-600">{reading.sensor}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge tone={statusTone(reading.status)}>{reading.status}</Badge>
          {reading.simulated && <Badge tone="warn">SIM</Badge>}
        </div>
      </div>

      <div className={`mt-3 text-3xl font-semibold ${stale ? 'text-slate-500' : 'text-slate-100'}`}>
        {display}
        {reading.unit && reading.value !== null && (
          <span className="ml-1 text-sm font-normal text-slate-400">{reading.unit}</span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
        <span>{formatRelative(reading.timestamp, now)}</span>
        {reading.detail && <span className="truncate pl-2 text-amber-400">{reading.detail}</span>}
      </div>
    </div>
  )
}
