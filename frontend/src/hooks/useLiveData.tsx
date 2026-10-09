import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../api/client'
import type {
  CommandRecord,
  EventRecord,
  SafetyResult,
  SystemStatus,
  TelemetryPoint,
  TelemetrySnapshot,
} from '../types'

const MAX_HISTORY = 180
const MAX_EVENTS = 300

interface LiveDataValue {
  connected: boolean
  mode: string
  simulated: boolean
  system: SystemStatus | null
  telemetry: TelemetrySnapshot | null
  history: TelemetryPoint[]
  latestDecision: SafetyResult | null
  latestCommand: CommandRecord | null
  events: EventRecord[]
  error: string | null
  lastMessageAt: number | null
  refresh: () => Promise<void>
}

const LiveDataContext = createContext<LiveDataValue | null>(null)

function pointFromSnapshot(snapshot: TelemetrySnapshot): TelemetryPoint {
  const num = (key: string): number | null => {
    const reading = snapshot.readings[key]
    if (!reading || reading.value === null || typeof reading.value === 'boolean') return null
    const value = Number(reading.value)
    return Number.isFinite(value) ? value : null
  }
  return {
    t: snapshot.timestamp ? new Date(snapshot.timestamp).getTime() : Date.now(),
    temperature_c: num('temperature_c'),
    humidity_percent: num('humidity_percent'),
    light_lux: num('light_lux'),
  }
}

export function LiveDataProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false)
  const [mode, setMode] = useState('simulation')
  const [simulated, setSimulated] = useState(true)
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [telemetry, setTelemetry] = useState<TelemetrySnapshot | null>(null)
  const [history, setHistory] = useState<TelemetryPoint[]>([])
  const [latestDecision, setLatestDecision] = useState<SafetyResult | null>(null)
  const [latestCommand, setLatestCommand] = useState<CommandRecord | null>(null)
  const [events, setEvents] = useState<EventRecord[]>([])
  const [error, setError] = useState<string | null>(null)
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null)

  const appendPoint = useCallback((point: TelemetryPoint) => {
    setHistory((prev) => {
      const next = [...prev, point]
      return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next
    })
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [status, latestTelemetry, decision] = await Promise.all([
        api.systemStatus(),
        api.telemetryLatest(),
        api.safetyLatest(),
      ])
      setSystem(status)
      setMode(status.simulated ? 'simulation' : 'hardware')
      setSimulated(status.simulated)
      if (latestTelemetry.available) setTelemetry(latestTelemetry)
      if (decision.available) setLatestDecision(decision)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reach backend')
    }
  }, [])

  // Seed chart history from persisted telemetry.
  useEffect(() => {
    let cancelled = false
    async function seed() {
      try {
        const [temp, humidity, light] = await Promise.all([
          api.telemetryHistory('temperature_c', MAX_HISTORY),
          api.telemetryHistory('humidity_percent', MAX_HISTORY),
          api.telemetryHistory('light_lux', MAX_HISTORY),
        ])
        if (cancelled) return
        const byTime = new Map<number, TelemetryPoint>()
        const upsert = (
          items: Array<{ value: string | null; timestamp: string }>,
          key: 'temperature_c' | 'humidity_percent' | 'light_lux',
        ) => {
          for (const item of items) {
            const t = new Date(item.timestamp).getTime()
            const existing =
              byTime.get(t) ?? { t, temperature_c: null, humidity_percent: null, light_lux: null }
            const parsed = item.value === null ? null : Number(item.value)
            existing[key] = parsed !== null && Number.isFinite(parsed) ? parsed : null
            byTime.set(t, existing)
          }
        }
        upsert(temp.items, 'temperature_c')
        upsert(humidity.items, 'humidity_percent')
        upsert(light.items, 'light_lux')
        const merged = Array.from(byTime.values()).sort((a, b) => a.t - b.t)
        setHistory(merged.slice(-MAX_HISTORY))
      } catch {
        // History seeding is best-effort.
      }
    }
    void seed()
    return () => {
      cancelled = true
    }
  }, [])

  // WebSocket connection with exponential backoff reconnect.
  useEffect(() => {
    let socket: WebSocket | null = null
    let closed = false
    let retry = 0
    let timer: number | undefined

    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${protocol}://${window.location.host}/ws`)

      socket.onopen = () => {
        retry = 0
        setConnected(true)
        setError(null)
      }

      socket.onmessage = (event) => {
        setLastMessageAt(Date.now())
        let message: { type: string; data: unknown }
        try {
          message = JSON.parse(event.data)
        } catch {
          return
        }
        switch (message.type) {
          case 'snapshot': {
            const data = message.data as {
              system: SystemStatus
              telemetry: TelemetrySnapshot | null
              decision: SafetyResult | null
              command: CommandRecord | null
              events: EventRecord[]
              simulated: boolean
              mode: string
            }
            setSystem(data.system)
            setSimulated(data.simulated)
            setMode(data.mode)
            if (data.telemetry) setTelemetry(data.telemetry)
            if (data.decision) setLatestDecision(data.decision)
            if (data.command) setLatestCommand(data.command)
            setEvents(data.events ?? [])
            break
          }
          case 'telemetry': {
            const snapshot = message.data as TelemetrySnapshot
            setTelemetry(snapshot)
            appendPoint(pointFromSnapshot(snapshot))
            break
          }
          case 'event': {
            const record = message.data as EventRecord
            setEvents((prev) => [record, ...prev].slice(0, MAX_EVENTS))
            break
          }
          case 'decision':
            setLatestDecision(message.data as SafetyResult)
            break
          case 'command':
            setLatestCommand(message.data as CommandRecord)
            break
          case 'system':
            setSystem(message.data as SystemStatus)
            break
          default:
            break
        }
      }

      socket.onclose = () => {
        setConnected(false)
        if (closed) return
        retry += 1
        const delay = Math.min(1000 * 2 ** (retry - 1), 10000)
        timer = window.setTimeout(connect, delay)
      }

      socket.onerror = () => {
        setError('WebSocket connection error')
      }
    }

    connect()
    return () => {
      closed = true
      if (timer) window.clearTimeout(timer)
      socket?.close()
    }
  }, [appendPoint])

  // Periodic REST refresh as a safety net for non-push fields.
  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => void refresh(), 8000)
    return () => window.clearInterval(interval)
  }, [refresh])

  const value = useMemo<LiveDataValue>(
    () => ({
      connected,
      mode,
      simulated,
      system,
      telemetry,
      history,
      latestDecision,
      latestCommand,
      events,
      error,
      lastMessageAt,
      refresh,
    }),
    [
      connected,
      mode,
      simulated,
      system,
      telemetry,
      history,
      latestDecision,
      latestCommand,
      events,
      error,
      lastMessageAt,
      refresh,
    ],
  )

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>
}

export function useLiveData(): LiveDataValue {
  const context = useContext(LiveDataContext)
  if (!context) {
    throw new Error('useLiveData must be used within a LiveDataProvider')
  }
  return context
}
