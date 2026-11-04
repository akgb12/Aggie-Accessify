import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import Dropzone from '../components/Dropzone'
import { Alert, PageContainer, PageHeader, Skeleton } from '../components/ui'
import { editorPath } from '../editorState'
import { errorMessage } from '../errors'
import { useDocumentTitle } from '../hooks'
import type { Project } from '../types'

const STEPS = [
  { title: 'Upload your slides', text: 'A .pptx deck, or a .zip with your .tex files, figures and style files.' },
  { title: 'Make them accessible', text: 'Choose a deck and an effort level. Larger decks take a few minutes.' },
  { title: 'Review and download', text: 'Check what changed, then download the same deck with the fixes inside.' },
]

// Opening a project means uploading its slides; everything after that happens in the editor
export default function ProjectPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useDocumentTitle(project?.name ?? 'Project')

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
      <div className="max-w-3xl">
        <PageHeader
          breadcrumbs={[{ label: 'Projects', to: '/' }, { label: project?.name ?? 'Project' }]}
          title={project?.name ?? 'Project'}
          subtitle="Upload the slides for this project. You choose which deck to make accessible next."
        />
        {error && (
          <div className="mb-6">
            <Alert tone="danger" title="The upload did not finish">
              {error}
            </Alert>
          </div>
        )}
        {project ? (
          <Dropzone busy={busy} onFiles={(files) => void upload(files)} />
        ) : (
          !error && <Skeleton className="h-64" />
        )}
        <section aria-labelledby="next-steps" className="mt-10">
          <h2 id="next-steps" className="text-lg font-semibold text-slate-900">
            What happens next
          </h2>
          <ol className="mt-4 grid gap-6 sm:grid-cols-3">
            {STEPS.map((step, index) => (
              <li key={step.title}>
                <span className="text-sm font-semibold text-brand-800">Step {index + 1}</span>
                <p className="mt-1 font-semibold text-slate-900">{step.title}</p>
                <p className="mt-1 text-sm text-slate-600">{step.text}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </PageContainer>
  )
}
