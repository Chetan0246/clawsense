import { NavLink, Outlet } from 'react-router-dom'
import {
  Activity,
  BrainCircuit,
  Gauge,
  History,
  LayoutDashboard,
  ShieldCheck,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { useLiveData } from '../hooks/useLiveData'
import { Badge, StateBadge } from './ui'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/sensors', label: 'Live Sensors', icon: Activity },
  { to: '/trace', label: 'AI Trace', icon: BrainCircuit },
  { to: '/safety', label: 'Safety Center', icon: ShieldCheck },
  { to: '/health', label: 'System Health', icon: Gauge },
  { to: '/events', label: 'Event History', icon: History },
]

function SimulationBanner({ simulated, mode }: { simulated: boolean; mode: string }) {
  if (!simulated) {
    return (
      <div className="flex items-center gap-2 border-b border-emerald-900 bg-emerald-950/50 px-4 py-1.5 text-xs text-emerald-300">
        <Activity className="h-3.5 w-3.5" />
        Hardware mode — data originates from a connected device.
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2 border-b border-amber-900 bg-amber-950/60 px-4 py-1.5 text-xs font-medium text-amber-200">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
      SIMULATION MODE — all sensor values and actuator results are simulated, not real
      hardware. Current mode: <span className="font-mono">{mode}</span>
    </div>
  )
}

export default function Layout() {
  const { connected, simulated, mode, system, error } = useLiveData()

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-800 bg-slate-900/80">
        <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-4">
          <ShieldCheck className="h-6 w-6 text-sky-400" />
          <div>
            <div className="text-sm font-bold tracking-wide text-slate-100">ClawSense</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">
              Control Center
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition ${
                  isActive
                    ? 'bg-sky-600/20 text-sky-300 ring-1 ring-sky-800'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-800 p-3 text-xs text-slate-500">
          <div className="flex items-center justify-between">
            <span>Transport</span>
            {connected ? (
              <Badge tone="ok">
                <Wifi className="h-3 w-3" /> live
              </Badge>
            ) : (
              <Badge tone="danger">
                <WifiOff className="h-3 w-3" /> down
              </Badge>
            )}
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span>Authority</span>
            <Badge tone={system?.controller_authority === 'agent' ? 'info' : 'warn'}>
              {system?.controller_authority ?? '—'}
            </Badge>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900/60 px-5 py-3">
          <div className="flex items-center gap-3">
            <h1 className="text-sm font-semibold text-slate-200">
              Supervisory Control &amp; Safety
            </h1>
            <StateBadge state={system?.current_state} />
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>
              Agent:{' '}
              <span className={system?.agent_available ? 'text-emerald-300' : 'text-red-300'}>
                {system?.agent_available ? 'available' : 'unavailable'}
              </span>
            </span>
            <span>
              Device:{' '}
              <span className={system?.device_connected ? 'text-emerald-300' : 'text-amber-300'}>
                {system?.device_connected ? 'connected' : 'unknown'}
              </span>
            </span>
          </div>
        </header>

        <SimulationBanner simulated={simulated} mode={mode} />

        {error && (
          <div className="border-b border-red-900 bg-red-950/50 px-5 py-1.5 text-xs text-red-200">
            Backend error: {error}
          </div>
        )}

        <main className="min-h-0 flex-1 overflow-y-auto p-5">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
