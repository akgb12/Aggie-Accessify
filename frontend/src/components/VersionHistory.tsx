import { Download, History } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, versionDownloadUrl } from '../api'
import { editorPath } from '../editorState'
import { errorMessage } from '../errors'
import { formatBytes, relativeTime } from '../format'
import type { FileVersion } from '../types'
import { versionSource } from '../versions'
import { buttonClasses, cx } from './classes'
import Modal from './Modal'
import { Alert, Badge, Button, Skeleton } from './ui'

interface Props {
  projectId: string
  path: string
  onClose: () => void
  // Called after a version is made current, so the file list and editor can catch up
  onChanged: () => void
}

// Every saved state of one file: what each came from, and a way to download or go back to it
export default function VersionHistory({ projectId, path, onClose, onChanged }: Props) {
  const [versions, setVersions] = useState<FileVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [restoring, setRestoring] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const name = path.split('/').pop() ?? path

  useEffect(() => {
    api
      .listVersions(projectId, path)
      .then(setVersions)
      .catch((e) => setError(errorMessage(e)))
  }, [projectId, path])

  async function restore(version: FileVersion) {
    setRestoring(version.id)
    setError(null)
    setMessage(null)
    try {
      const updated = await api.restoreVersion(projectId, version.id)
      setVersions(updated)
      setMessage(`Version ${version.number} is current again, saved as version ${updated[0].number}.`)
      onChanged()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setRestoring(null)
    }
  }

  return (
    <Modal title={`Version history of ${name}`} onClose={onClose} className="max-w-xl">
      <div className="space-y-4 px-6 pb-6 pt-2">
        <p className="text-sm text-slate-600">
          Every upload and every accessible result is kept. Runs start from the current version, so changes you
          upload are built on. Making an older version current adds it as a new version; nothing is deleted.
        </p>
        {error && <Alert tone="danger">{error}</Alert>}
        {message && <Alert tone="success">{message}</Alert>}
        {!versions && !error && <Skeleton className="h-32" />}
        {versions && (
          <ol className="divide-y divide-slate-200 rounded-lg border border-slate-200">
            {versions.map((version) => (
              <li key={version.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 p-3">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    Version {version.number}
                    {version.current && <Badge tone="brand">Current</Badge>}
                  </p>
                  <p className="text-sm text-slate-600">
                    {versionSource(version)} · {relativeTime(version.created_at)} · {formatBytes(version.size)}
                  </p>
                  {version.run_id && (
                    <Link
                      to={editorPath(projectId, path, version.run_id)}
                      onClick={onClose}
                      className="text-sm font-semibold text-brand-800 underline underline-offset-4"
                    >
                      Open the results that made it
                    </Link>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  <a
                    href={versionDownloadUrl(projectId, version.id)}
                    aria-label={`Download version ${version.number}`}
                    className={cx(buttonClasses('secondary', 'sm'), 'h-8 px-2.5 text-sm')}
                  >
                    <Download aria-hidden className="h-4 w-4" />
                    Download
                  </a>
                  {!version.current && (
                    <Button
                      size="sm"
                      loading={restoring === version.id}
                      disabled={restoring !== null}
                      onClick={() => void restore(version)}
                      icon={<History aria-hidden className="h-4 w-4" />}
                      aria-label={`Make version ${version.number} current`}
                    >
                      Make current
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Modal>
  )
}
