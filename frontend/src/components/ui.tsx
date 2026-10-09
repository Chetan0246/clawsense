import { useEffect, useState, type ReactNode } from 'react'
import type { CheckStatus, SystemStateName } from '../types'

// ---------------------------------------------------------------------------
// Small live-updating clock for relative timestamps.
// ---------------------------------------------------------------------------
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return now
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString([], { hour12: false })
}

export function formatRelative(iso: string | null | undefined, now: number): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'never'
  const seconds = Math.max(0, Math.round((now - then) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

// ---------------------------------------------------------------------------
// Layout primitives
// ---------------------------------------------------------------------------
export function Panel({
  title,
  actions,
  children,
  className = '',
  bodyClassName = 'p-4',
}: {
  title?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-header">
          <h2 className="panel-title">{title}</h2>
          {actions}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
      {label && <span>{label}</span>}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center rounded-md border border-dashed border-slate-700 py-8 text-sm text-slate-500">
      {message}
    </div>
  )
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-red-800 bg-red-950/60 px-4 py-2 text-sm text-red-200">
      <span>{message}</span>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Status / tone helpers
// ---------------------------------------------------------------------------
type Tone = 'neutral' | 'ok' | 'warn' | 'danger' | 'info'

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'bg-slate-700 text-slate-200',
  ok: 'bg-emerald-600/20 text-emerald-300 ring-1 ring-emerald-700',
  warn: 'bg-amber-600/20 text-amber-300 ring-1 ring-amber-700',
  danger: 'bg-red-600/20 text-red-300 ring-1 ring-red-700',
  info: 'bg-sky-600/20 text-sky-300 ring-1 ring-sky-700',
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge ${TONE_CLASSES[tone]}`}>{children}</span>
}

export const STATE_TONE: Record<SystemStateName, Tone> = {
  ONLINE_AGENT: 'ok',
  DEGRADED: 'warn',
  OFFLINE_LOCAL: 'info',
  RECOVERY: 'info',
  SAFE_LOCKDOWN: 'danger',
}

export function StateBadge({ state }: { state: SystemStateName | null | undefined }) {
  if (!state) return <Badge tone="neutral">UNKNOWN</Badge>
  return <Badge tone={STATE_TONE[state]}>{state.replace('_', ' ')}</Badge>
}

export const CHECK_TONE: Record<CheckStatus, Tone> = {
  PASS: 'ok',
  FAIL: 'danger',
  SKIP: 'neutral',
}

export function CheckBadge({ status }: { status: CheckStatus }) {
  return <Badge tone={CHECK_TONE[status]}>{status}</Badge>
}

export function severityTone(severity: string): Tone {
  switch (severity) {
    case 'critical':
    case 'error':
      return 'danger'
    case 'warning':
      return 'warn'
    case 'debug':
      return 'neutral'
    default:
      return 'info'
  }
}

// ---------------------------------------------------------------------------
// Metric card
// ---------------------------------------------------------------------------
export function StatCard({
  label,
  value,
  unit,
  hint,
  tone = 'neutral',
  icon,
}: {
  label: string
  value: ReactNode
  unit?: string
  hint?: ReactNode
  tone?: Tone
  icon?: ReactNode
}) {
  const accent: Record<Tone, string> = {
    neutral: 'text-slate-100',
    ok: 'text-emerald-300',
    warn: 'text-amber-300',
    danger: 'text-red-300',
    info: 'text-sky-300',
  }
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-400">
        <span>{label}</span>
        {icon}
      </div>
      <div className={`mt-2 flex items-baseline gap-1 text-2xl font-semibold ${accent[tone]}`}>
        <span>{value}</span>
        {unit && <span className="text-sm font-normal text-slate-400">{unit}</span>}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stale indicator
// ---------------------------------------------------------------------------
export function StaleIndicator({
  ageSeconds,
  maxAgeSeconds = 30,
}: {
  ageSeconds: number | null | undefined
  maxAgeSeconds?: number
}) {
  if (ageSeconds === null || ageSeconds === undefined) {
    return <Badge tone="neutral">no data</Badge>
  }
  if (ageSeconds > maxAgeSeconds) {
    return <Badge tone="danger">STALE {ageSeconds.toFixed(0)}s</Badge>
  }
  return <Badge tone="ok">live {ageSeconds.toFixed(0)}s</Badge>
}
