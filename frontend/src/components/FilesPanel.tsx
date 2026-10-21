import { Upload } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { errorMessage } from '../errors'
import type { WorkspaceData } from '../workspace'
import FileTree from './FileTree'
import { Spinner } from './ui'

interface Props {
  projectId: string
  data: WorkspaceData
  selectedFile: string | null
  onSelect: (path: string) => void
  // Called after a file is removed, so the editor can leave a file that no longer exists
  onRemoved: (path: string) => void
}

export default function FilesPanel({ projectId, data, selectedFile, onSelect, onRemoved }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function upload(files: File[]) {
    if (files.length === 0) return
    setBusy(true)
    setError(null)
    try {
      await api.uploadFiles(projectId, files)
      data.reload()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function remove(path: string) {
    if (!window.confirm(`Remove ${path} from this project?`)) return
    try {
      await api.removeFile(projectId, path)
      data.reload()
      onRemoved(path)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-1.5 border-b border-slate-100 p-2.5">
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 has-[:disabled]:opacity-50">
          {busy ? <Spinner /> : <Upload aria-hidden className="h-4 w-4" />}
          Add files or a .zip
          <input
            type="file"
            multiple
            disabled={busy}
            className="sr-only"
            aria-label="Add files or a zip to this project"
            onChange={(event) => {
              void upload(Array.from(event.target.files ?? []))
              event.target.value = ''
            }}
          />
        </label>
        {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
        <p className="text-xs text-slate-400">
          Maroon files are Beamer presentations. Click one to open it.
        </p>
      </div>
      <div className="min-h-0 flex-1 overflow-auto pt-1">
        {data.project ? (
          <FileTree
            files={data.project.files}
            targets={data.targets}
            latestByFile={data.latestByFile}
            selectedFile={selectedFile}
            onSelect={onSelect}
            onRemove={(path) => void remove(path)}
          />
        ) : (
          <p className="p-4 text-sm text-slate-500">{data.error ?? 'Loading files…'}</p>
        )}
      </div>
    </div>
  )
}
