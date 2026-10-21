import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { errorMessage } from './errors'
import type { Project, Run } from './types'

export interface WorkspaceData {
  project: Project | null
  // Beamer files that can be translated
  targets: string[]
  runs: Run[]
  // The newest run of each translated file
  latestByFile: Map<string, Run>
  error: string | null
  reload: () => void
}

export function latestRunsByFile(runs: Run[]): Map<string, Run> {
  const latest = new Map<string, Run>()
  const sorted = [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at))
  for (const run of sorted) {
    if (run.main_file && !latest.has(run.main_file)) latest.set(run.main_file, run)
  }
  return latest
}

export function useWorkspaceData(projectId: string): WorkspaceData {
  const [project, setProject] = useState<Project | null>(null)
  const [targets, setTargets] = useState<string[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.getProject(projectId), api.targets(projectId), api.listRuns(projectId)])
      .then(([nextProject, nextTargets, nextRuns]) => {
        if (cancelled) return
        setProject(nextProject)
        setTargets(nextTargets.candidates)
        setRuns(nextRuns)
        setError(null)
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e))
      })
    return () => {
      cancelled = true
    }
  }, [projectId, version])

  const latestByFile = useMemo(() => latestRunsByFile(runs), [runs])
  const reload = useCallback(() => setVersion((value) => value + 1), [])
  return { project, targets, runs, latestByFile, error, reload }
}
