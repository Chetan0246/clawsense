// Types mirroring the ClawSense backend API contract.

export type SystemStateName =
  | 'ONLINE_AGENT'
  | 'DEGRADED'
  | 'OFFLINE_LOCAL'
  | 'RECOVERY'
  | 'SAFE_LOCKDOWN'

export type CheckStatus = 'PASS' | 'FAIL' | 'SKIP'

export type SensorStatus =
  | 'OK'
  | 'STALE'
  | 'ERROR'
  | 'NOT_CONFIGURED'
  | 'UNAVAILABLE'

export interface CheckResult {
  name: string
  status: CheckStatus
  detail: string
  code: string | null
  timestamp: string
  proposal_id: string | null
}

export interface SafetyResult {
  decision_id: string
  proposal_id: string
  approved: boolean
  reason_code: string
  reason: string
  checks: Record<string, CheckStatus>
  check_results: CheckResult[]
  timestamp: string
  dispatch_attempted: boolean
  available?: boolean
}

export interface SensorReading {
  sensor: string
  value: number | boolean | string | null
  unit: string
  status: SensorStatus
  timestamp: string
  simulated: boolean
  detail: string
}

export interface TelemetrySnapshot {
  device_id: string
  timestamp: string | null
  simulated: boolean
  readings: Record<string, SensorReading>
  available?: boolean
  age_seconds?: number | null
}

export interface SystemStatus {
  current_state: SystemStateName
  previous_state: SystemStateName | null
  transition_reason_code: string | null
  transition_reason: string | null
  last_transition_at: string | null
  controller_authority: 'agent' | 'local' | 'none'
  agent_available: boolean
  agent_provider: string
  network_available: boolean
  device_connected: boolean
  last_successful_agent_request: string | null
  last_successful_device_communication: string | null
  recovery_status: string
  simulated: boolean
  uptime_seconds: number
}

export interface EventRecord {
  event_id: string
  timestamp: string
  event_type: string
  category: string
  source: string
  severity: 'debug' | 'info' | 'warning' | 'error' | 'critical'
  device_id: string | null
  proposal_id: string | null
  command_id: string | null
  details: Record<string, unknown>
  simulated: boolean
}

export interface CommandRecord {
  command_id: string
  proposal_id: string
  decision_id: string
  target_device: string
  action: string
  parameters: Record<string, unknown>
  status: string
  dispatched_at: string | null
  acknowledged_at: string | null
  error: string | null
  simulated: boolean
  created_at: string
}

export interface ActionProposal {
  proposal_id: string
  action: string
  parameters: Record<string, unknown>
  reason: string
  source: string
  created_at: string
}

export interface StateTransition {
  transition_id: string
  previous_state: SystemStateName | null
  new_state: SystemStateName
  reason_code: string
  reason: string
  timestamp: string
  simulated: boolean
  diagnostics: Record<string, unknown>
}

export interface TelemetryPoint {
  t: number
  temperature_c: number | null
  humidity_percent: number | null
  light_lux: number | null
}

export interface HealthInfo {
  status: string
  version: string
  mode: string
  simulated: boolean
  current_state: SystemStateName
  uptime_seconds: number
  websocket_subscribers: number
  control_cycles: number
  control_errors: number
}

export interface SafetyTestResult {
  key: string
  name: string
  description: string
  payload: Record<string, unknown>
  system_state: SystemStateName
  expected: { approved: boolean; reason_codes: string[] }
  result: SafetyResult
  passed: boolean
}

export interface SafetyTestReport {
  kind: string
  hardware_tested: boolean
  total: number
  passed: number
  results: SafetyTestResult[]
}

export interface SimulationState {
  mode: string
  simulated: boolean
  device: {
    device_id: string
    firmware_version: string
    scenario: string
    servo_angle: number
    buzzer_active: boolean
    buzzer_duration_ms: number
    led_color: string
    simulated: boolean
  } | null
  agent_provider: string
  agent_mode: string | null
  transport_failure_mode: string | null
}
