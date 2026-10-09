// Thin REST client. All requests go through the Vite dev proxy to the backend.
// The browser never holds an LLM API key — the backend owns all secrets.

import type {
  ActionProposal,
  EventRecord,
  HealthInfo,
  SafetyResult,
  SafetyTestReport,
  SimulationState,
  StateTransition,
  SystemStateName,
  SystemStatus,
  TelemetrySnapshot,
  CommandRecord,
} from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      // keep the status text
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<HealthInfo>('/api/v1/health'),

  systemStatus: () => request<SystemStatus>('/api/v1/system/status'),

  transitions: (limit = 50) =>
    request<{ items: StateTransition[]; total: number }>(
      `/api/v1/system/transitions?limit=${limit}`,
    ),

  lockdown: () =>
    request<StateTransition>('/api/v1/system/lockdown', { method: 'POST' }),

  reset: () => request<StateTransition>('/api/v1/system/reset', { method: 'POST' }),

  telemetryLatest: () => request<TelemetrySnapshot>('/api/v1/telemetry/latest'),

  telemetryHistory: (sensor: string, limit = 120) =>
    request<{ items: Array<{ sensor: string; value: string | null; timestamp: string }> }>(
      `/api/v1/telemetry/history?sensor=${encodeURIComponent(sensor)}&limit=${limit}`,
    ),

  safetyLatest: () => request<SafetyResult>('/api/v1/safety/latest'),

  safetyDecisions: (limit = 50) =>
    request<{ items: SafetyResult[]; total: number }>(
      `/api/v1/safety/decisions?limit=${limit}`,
    ),

  safetyValidate: (payload: Record<string, unknown>) =>
    request<SafetyResult>('/api/v1/safety/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  safetyTest: () =>
    request<SafetyTestReport>('/api/v1/safety/test', { method: 'POST' }),

  safetyEvents: (limit = 100) =>
    request<{ items: EventRecord[]; total: number }>(
      `/api/v1/safety/events?limit=${limit}`,
    ),

  propose: (action: string, parameters: Record<string, unknown>, reason: string) =>
    request<{ decision: SafetyResult; command: CommandRecord | null }>(
      '/api/v1/actions/propose',
      {
        method: 'POST',
        body: JSON.stringify({ action, parameters, reason }),
      },
    ),

  commands: (limit = 50) =>
    request<{ items: CommandRecord[]; total: number }>(
      `/api/v1/actions/commands?limit=${limit}`,
    ),

  proposals: (limit = 50) =>
    request<{ items: ActionProposal[]; total: number }>(
      `/api/v1/actions/proposals?limit=${limit}`,
    ),

  events: (params: {
    category?: string
    severity?: string
    search?: string
    proposal_id?: string
    limit?: number
    offset?: number
  }) => {
    const query = new URLSearchParams()
    if (params.category) query.set('category', params.category)
    if (params.severity) query.set('severity', params.severity)
    if (params.search) query.set('search', params.search)
    if (params.proposal_id) query.set('proposal_id', params.proposal_id)
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return request<{ items: EventRecord[]; total: number; limit: number; offset: number }>(
      `/api/v1/events?${query.toString()}`,
    )
  },

  simulationState: () => request<SimulationState>('/api/v1/simulation/state'),

  setScenario: (scenario: string) =>
    request<{ scenario: string }>('/api/v1/simulation/scenario', {
      method: 'POST',
      body: JSON.stringify({ scenario }),
    }),

  setAgentMode: (mode: string) =>
    request<{ agent_mode: string }>('/api/v1/simulation/agent', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),

  setAgentAvailability: (available: boolean) =>
    request<{ agent_available: boolean }>('/api/v1/simulation/agent/availability', {
      method: 'POST',
      body: JSON.stringify({ available }),
    }),

  setFailureMode: (mode: string) =>
    request<{ failure_mode: string }>('/api/v1/simulation/failure', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),

  forceState: (state: SystemStateName, reason: string) =>
    request<StateTransition>('/api/v1/system/state', {
      method: 'POST',
      body: JSON.stringify({ state, reason_code: 'MANUAL_OVERRIDE', reason }),
    }),

  eventsExportUrl: (category?: string, severity?: string) => {
    const query = new URLSearchParams()
    if (category) query.set('category', category)
    if (severity) query.set('severity', severity)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return `/api/v1/events/export.csv${suffix}`
  },
}
