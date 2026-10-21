import type { ProjectFile, Run } from './types'

// The file shown in the editor: the one asked for, the only presentation, or the last one translated
export function pickFile(
  requested: string | null,
  targets: string[],
  runs: Run[],
): string | null {
  if (requested && targets.includes(requested)) return requested
  if (targets.length === 1) return targets[0]
  const newest = [...runs]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .find((run) => run.main_file && targets.includes(run.main_file))
  return newest?.main_file ?? null
}

export type NoTargetsReason = 'no_tex' | 'no_beamer'

// Why a project has nothing to translate, from its files alone
export function whyNoTargets(files: ProjectFile[], targets: string[]): NoTargetsReason | null {
  if (targets.length > 0 || files.length === 0) return null
  return files.some((file) => file.path.toLowerCase().endsWith('.tex')) ? 'no_beamer' : 'no_tex'
}

export function editorPath(projectId: string, file: string | null, runId?: string | null): string {
  const query = new URLSearchParams()
  if (file) query.set('file', file)
  if (runId) query.set('run', runId)
  const text = query.toString()
  return `/projects/${projectId}/editor${text ? `?${text}` : ''}`
}
