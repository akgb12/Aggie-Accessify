import { useCallback } from 'react'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import EditorFrame from '../components/EditorFrame'
import EditorMain from '../components/EditorMain'
import EditorToolbar from '../components/EditorToolbar'
import FilesPanel from '../components/FilesPanel'
import ReviewView from '../components/ReviewView'
import { Alert, Skeleton } from '../components/ui'
import { editorPath, pickFile } from '../editorState'
import { usePersistentFlag } from '../hooks'
import type { Run } from '../types'
import { useRun } from '../useRun'
import { useWorkspaceData } from '../workspace'

export default function EditorPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const workspace = useWorkspaceData(id)
  const [leftOpen, setLeftOpen] = usePersistentFlag('review.left', true)

  const { project, targets, runs, latestByFile, reload } = workspace
  const file = pickFile(params.get('file'), targets, runs)
  const runId = params.get('run') ?? (file ? (latestByFile.get(file)?.id ?? null) : null)
  const followed = useRun(runId, reload)

  const select = useCallback((path: string) => navigate(editorPath(id, path)), [id, navigate])
  const started = useCallback(
    (run: Run) => {
      reload()
      navigate(editorPath(id, run.main_file || file, run.id))
    },
    [id, file, navigate, reload],
  )

  if (!project) {
    return workspace.error ? (
      <div className="p-6">
        <Alert tone="danger" title="Could not load this project">
          {workspace.error}
        </Alert>
      </div>
    ) : (
      <div className="space-y-4 p-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-56" />
      </div>
    )
  }
  if (project.files.length === 0) return <Navigate to={`/projects/${id}`} replace />

  const files = (
    <FilesPanel
      projectId={id}
      data={workspace}
      selectedFile={file}
      onSelect={select}
      onRemoved={(path) => {
        if (path === file) navigate(editorPath(id, null), { replace: true })
      }}
    />
  )

  if (followed.run?.status === 'succeeded' && followed.review) {
    return (
      <ReviewView
        key={followed.run.id}
        run={followed.run}
        review={followed.review}
        projectName={project.name}
        workspace={workspace}
        files={files}
        onStarted={started}
      />
    )
  }

  return (
    <EditorFrame
      toolbar={
        <EditorToolbar
          projectName={project.name}
          file={file}
          leftOpen={leftOpen}
          onToggleLeft={() => setLeftOpen(!leftOpen)}
        />
      }
      left={leftOpen ? files : null}
      center={
        <EditorMain
          project={project}
          targets={targets}
          file={file}
          run={followed.run}
          loadError={followed.error}
          onSelect={select}
          onStarted={started}
        />
      }
      right={null}
    />
  )
}
