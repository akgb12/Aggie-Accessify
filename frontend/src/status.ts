import type { ElementStatus } from './types'

interface StatusStyle {
  label: string
  color: string
  // SVG dash pattern so status never relies on color alone
  dash: string
}

// Only the TAMU status colors; dash patterns keep every status distinct without color
export const STATUS_STYLES: Record<ElementStatus, StatusStyle> = {
  done: { label: 'Done', color: '#166534', dash: '' },
  deterministic: { label: 'Done', color: '#166534', dash: '' },
  model_generated: { label: 'Described by AI', color: '#1e40af', dash: '' },
  needs_description: { label: 'Needs a description', color: '#92400e', dash: '7 4' },
  needs_review: { label: 'Needs review', color: '#92400e', dash: '2 3' },
  failed: { label: 'Failed', color: '#b91c1c', dash: '10 3 2 3' },
  missing_asset: { label: 'Missing file', color: '#b91c1c', dash: '4 4' },
  not_handled: { label: 'Not handled', color: '#626262', dash: '1 4' },
}

// Legend entries: deterministic is folded into done
export const LEGEND_STATUSES: ElementStatus[] = [
  'done',
  'model_generated',
  'needs_description',
  'needs_review',
  'failed',
  'missing_asset',
  'not_handled',
]

const FALLBACK: StatusStyle = { label: 'Unknown', color: '#626262', dash: '' }

export function statusStyle(status: string): StatusStyle {
  return STATUS_STYLES[status as ElementStatus] ?? FALLBACK
}

export function statusColor(status: string): string {
  return statusStyle(status).color
}

export function statusLabel(status: string): string {
  return statusStyle(status).label
}

// deterministic elements are reported with done
export function statusGroup(status: string): ElementStatus {
  return status === 'deterministic' ? 'done' : (status as ElementStatus)
}

// Statuses a reviewer should look at first
export function needsAttention(status: string): boolean {
  return !['done', 'deterministic', 'model_generated'].includes(status)
}

const SEVERITY_ORDER = ['veto', 'error', 'warning', 'info']

export function severityRank(severity: string): number {
  const index = SEVERITY_ORDER.indexOf(severity)
  return index === -1 ? SEVERITY_ORDER.length : index
}

export function isFinished(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'blocked'
}
