import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import Dropzone from '../components/Dropzone'
import { Alert, PageContainer, PageHeader, Skeleton } from '../components/ui'
import { editorPath } from '../editorState'
import { errorMessage } from '../errors'
import type { Project } from '../types'

// Opening a project means uploading its slides; everything after that happens in the editor
export default function ProjectPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getProject(id)
      .then(setProject)
      .catch((e) => setError(errorMessage(e)))
  }, [id])

  async function upload(files: File[]) {
    setBusy(true)
    setError(null)
    try {
      await api.uploadFiles(id, files)
      navigate(editorPath(id, null))
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  if (project && project.files.length > 0) return <Navigate to={editorPath(id, null)} replace />

  return (
    <PageContainer>
      <PageHeader
        breadcrumbs={[{ label: 'Projects', to: '/' }, { label: project?.name ?? 'Project' }]}
        title={project?.name ?? 'Project'}
        subtitle="Upload your slides. You will choose what to translate in the editor."
      />
      {error && (
        <div className="mb-4">
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        </div>
      )}
      {project ? (
        <Dropzone busy={busy} onFiles={(files) => void upload(files)} />
      ) : (
        !error && <Skeleton className="h-48" />
      )}
      <p className="mt-3 text-sm text-slate-500">
        Upload a PowerPoint (.pptx) deck, or a .zip of the whole LaTeX project (.tex files, figures and style files).
      </p>
    </PageContainer>
  )
}
