// Types matching the Django Ninja schemas and review payload from the backend

export type RunStatus = 'queued' | 'running' | 'blocked' | 'succeeded' | 'failed'
export type Effort = 'baseline' | 'low' | 'medium' | 'high'

export type DefaultEffort = Exclude<Effort, 'baseline'>

export interface Preferences {
  default_effort: DefaultEffort
  show_demo_options: boolean
}

export interface User {
  id: number
  username: string
  first_name: string
  last_name: string
  preferences: Preferences
  created_at: string
}

export interface Registration {
  username: string
  first_name: string
  last_name: string
  password: string
  confirm_password: string
}

export interface Usage {
  projects: number
  runs: number
  succeeded_runs: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
  cost_usd_this_month: number
  // The account's hard limit on model spend, what it has spent in total, and what is left
  limit_usd: number
  spent_usd: number
  remaining_usd: number
}

export interface ProjectFile {
  id: number
  path: string
  size: number
  sha256: string
  uploaded_at: string
  // The current version's number, and how many versions the file has
  version: number | null
  versions: number
}

export interface FileVersion {
  id: string
  number: number
  source: 'upload' | 'update' | 'restore'
  created_at: string
  size: number
  current: boolean
  run_id: string | null
  run_effort: Effort | null
  run_a_score: number | null
  restored_from: number | null
}

// What a finished run did with the file it made accessible; empty for runs from before versions
export type VersionOutcome = '' | 'saved' | 'saved_not_current' | 'unchanged' | 'not_saved'

export interface Project {
  id: string
  name: string
  created_at: string
  updated_at: string
  files: ProjectFile[]
}

export interface PreflightIssue {
  code: string
  severity: string
  message: string
  source_file: string | null
  line: number | null
  dependency: string | null
}

export interface PreflightProblem {
  code: 'no_tex_files' | 'no_beamer_main' | 'choose_main_file'
  message: string
}

export interface Preflight {
  ok: boolean
  main_file: string | null
  main_candidates: string[]
  problem: PreflightProblem | null
  missing_images: string[]
  critical_blockers: string[]
  issues: PreflightIssue[]
}

export interface Run {
  id: string
  project_id: string
  status: RunStatus
  effort: Effort
  main_file: string
  seed_weak: string | null
  model_provider: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  storage_prefix: string
  stop_reason: string
  a_score: number | null
  f_score: number | null
  input_tokens: number
  output_tokens: number
  cost_usd: string
  error_message: string
  input_version: number | null
  output_version: number | null
  version_outcome: VersionOutcome
}

export interface RunCreate {
  effort: Effort
  main_file?: string | null
  seed_weak?: string | null
  fresh?: boolean
}

export type ElementStatus =
  | 'done'
  | 'deterministic'
  | 'needs_description'
  | 'model_generated'
  | 'needs_review'
  | 'failed'
  | 'missing_asset'
  | 'not_handled'

// PDF points, origin bottom-left: x0, y0, x1, y1
export type Bbox = [number, number, number, number]
export type Anchor = [number, number]

export interface ReviewIssue {
  code: string
  message: string
  severity: string
  element_id: string | null
  details?: Record<string, unknown>
}

export interface HistoryEntry {
  round?: number
  by?: string
  change?: string
  model?: string | null
  input_tokens?: number
  output_tokens?: number
  cost_usd?: number
}

export interface ReviewElement {
  id: string
  type: string
  // Finer kind, such as chart, equation or the document outline
  subtype?: string | null
  role: string | null
  text: string | null
  status: ElementStatus
  pages: number[]
  bbox: Bbox | null
  anchor: Anchor | null
  alt: string | null
  extended_description: string | null
  visible_pages: number[] | null
  // The picture a description was written for (PowerPoint and Word runs)
  image_url: string | null
  source: { file: string | null; line_start: number | null; line_end: number | null } | null
  history: HistoryEntry[]
  issues: ReviewIssue[]
  // What the update did besides writing text: a header row, a heading, a decorative mark
  note?: string | null
}

export interface ReviewContainer {
  id: string
  kind: string
  element_ids: string[]
  rendered_pages: number[]
  title_element_id: string | null
}

export interface ReviewPage {
  number: number
  image_url: string
  thumb_url: string
  width_points: number
  height_points: number
}

export interface ReviewOutput {
  label: string
  path: string
}

export interface Review {
  run_id: string
  render_engine: string | null
  source_format: 'tex-beamer' | 'pptx' | 'docx'
  outputs: ReviewOutput[]
  containers: ReviewContainer[]
  elements: ReviewElement[]
  pages: ReviewPage[]
  scores: { accessibility: number | null; fidelity: number | null }
  stop_reason: string
  round_history: unknown[]
  issues: ReviewIssue[]
  // True while an older run gains the downloads added since it finished
  refreshing?: boolean
}
