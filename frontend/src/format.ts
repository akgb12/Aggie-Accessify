const UNITS = ['B', 'KB', 'MB', 'GB']

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '–'
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1
  return `${value.toFixed(digits)} ${UNITS[unit]}`
}

const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  if (Number.isNaN(seconds)) return '–'
  if (Math.abs(seconds) < 45) return 'just now'
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  }
  return formatter.format(Math.round(seconds / 60), 'minute')
}

export function formatDuration(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return minutes > 0 ? `${minutes}m ${seconds.toString().padStart(2, '0')}s` : `${seconds}s`
}

export function formatCost(value: string | number): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '–'
  return amount === 0 ? '$0.00' : `$${amount.toFixed(amount < 0.01 ? 4 : 2)}`
}

export type ScoreTone = 'success' | 'warning' | 'danger'

export function scoreTone(score: number | null): ScoreTone {
  if (score === null) return 'warning'
  if (score >= 90) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}

export function fileKind(path: string): 'tex' | 'deck' | 'document' | 'pdf' | 'image' | 'style' | 'other' {
  const extension = path.split('.').pop()?.toLowerCase() ?? ''
  if (extension === 'tex') return 'tex'
  if (extension === 'pptx') return 'deck'
  if (extension === 'docx') return 'document'
  if (extension === 'pdf') return 'pdf'
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'eps', 'webp'].includes(extension)) return 'image'
  if (['sty', 'cls', 'bst', 'bib'].includes(extension)) return 'style'
  return 'other'
}

export function shortElementId(id: string): string {
  const parts = id.split('/')
  return parts[parts.length - 1] || id
}

const TYPE_LABELS: Record<string, string> = {
  title_page: 'Title page',
  document_title: 'Title',
  heading: 'Slide title',
  paragraph: 'Text',
  list: 'List',
  list_item: 'Bullet',
  figure: 'Figure',
  formula: 'Formula',
  table: 'Table',
  block: 'Block',
  unknown: 'Unsupported content',
}

export function typeLabel(type: string): string {
  const known = TYPE_LABELS[type]
  if (known) return known
  const spaced = type.replace(/_/g, ' ').trim()
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : 'Element'
}

function stripIndex(segment: string): string {
  return segment.replace(/_\d+$/, '')
}

// The title of a slide or section. A Word section starts at a line that looked like a
// heading, and that line names the section only if it is a heading now.
export function containerTitle(
  container: { id: string; title_element_id: string | null },
  elementsById: Map<string, { type: string; text: string | null; role?: string | null }>,
): string {
  const element = container.title_element_id ? elementsById.get(container.title_element_id) : undefined
  if (!element?.text) return ''
  const named =
    !container.id.startsWith('section_') ||
    ['heading', 'document_title'].includes(element.type) ||
    /^H\d$/.test(element.role ?? '')
  return named ? element.text : ''
}

// "slide_04" becomes "Slide 4"
export function containerLabel(id: string): string {
  const match = /^(.*?)_0*(\d+)$/.exec(id)
  if (!match) return typeLabel(id)
  const name = typeLabel(match[1])
  return `${name} ${match[2]}`
}

export interface ElementLabel {
  title: string
  subtitle: string
}

const SUBTYPE_LABELS: Record<string, string> = {
  document_outline: 'Document outline',
  equation: 'Equation',
  chart: 'Chart',
}

// What kind of element this is: a heading in a Word section is not a slide title, and a
// line made into a heading says its level
function kindLabel(element: { id: string; type: string; subtype?: string | null; role?: string | null }): string {
  const special = element.subtype ? SUBTYPE_LABELS[element.subtype] : undefined
  if (special) return special
  if (element.id.startsWith('section_')) {
    const level = /^H([1-6])$/.exec(element.role ?? '')
    if (level) return `Heading ${level[1]}`
    if (element.type === 'heading') return 'Heading'
  }
  return typeLabel(element.type)
}

// Human wording for an element, so raw ids like slide_01/title_page_01/paragraph_03 stay hidden
export function elementLabel(element: {
  id: string
  type: string
  text: string | null
  subtype?: string | null
  role?: string | null
  alt?: string | null
}): ElementLabel {
  const segments = element.id.split('/')
  const kind = kindLabel(element)
  const where = [containerLabel(segments[0])]
  for (const segment of segments.slice(1, -1)) where.push(typeLabel(stripIndex(segment)))
  // A figure or equation has no text of its own, so its description names it
  const excerpt = (element.text || element.alt)?.replace(/\s+/g, ' ').trim()
  if (excerpt) {
    const short = excerpt.length > 70 ? `${excerpt.slice(0, 69)}…` : excerpt
    return { title: short, subtitle: [...where, kind].join(' · ') }
  }
  return { title: kind, subtitle: where.join(' · ') }
}
