import { useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Alert, PageContainer, Skeleton } from '../components/ui'
import { editorPath } from '../editorState'
import { errorMessage } from '../errors'
import type { Run } from '../types'

// Old /runs/:id links open the same translation in the editor
export default function RunRedirect() {
  const { id = '' } = useParams()
  const [run, setRun] = useState<Run | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getRun(id)
      .then(setRun)
      .catch((e) => setError(errorMessage(e)))
  }, [id])

  if (run) return <Navigate to={editorPath(run.project_id, run.main_file || null, run.id)} replace />
  return (
    <PageContainer>
      {error ? (
        <Alert tone="danger" title="This run could not be loaded">
          {error}
        </Alert>
      ) : (
        <Skeleton className="h-40" />
      )}
    </PageContainer>
  )
}
