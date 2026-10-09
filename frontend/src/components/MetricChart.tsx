import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TelemetryPoint } from '../types'
import { EmptyState } from './ui'

export function MetricChart({
  data,
  dataKey,
  label,
  unit,
  color,
  domain,
  height = 200,
}: {
  data: TelemetryPoint[]
  dataKey: 'temperature_c' | 'humidity_percent' | 'light_lux'
  label: string
  unit: string
  color: string
  domain?: [number | 'auto', number | 'auto']
  height?: number
}) {
  const series = data.filter((point) => point[dataKey] !== null)
  if (series.length === 0) {
    return <EmptyState message={`Waiting for ${label.toLowerCase()} data…`} />
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(value: number) =>
            new Date(value).toLocaleTimeString([], {
              hour12: false,
              minute: '2-digit',
              second: '2-digit',
            })
          }
          stroke="#475569"
          fontSize={11}
          minTickGap={40}
        />
        <YAxis
          stroke="#475569"
          fontSize={11}
          domain={domain ?? ['auto', 'auto']}
          tickFormatter={(value: number) => `${value}`}
        />
        <Tooltip
          contentStyle={{
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: 6,
            fontSize: 12,
          }}
          labelFormatter={(value) =>
            new Date(Number(value)).toLocaleTimeString([], { hour12: false })
          }
          formatter={(value) => [`${value} ${unit}`, label]}
        />
        <Line
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
