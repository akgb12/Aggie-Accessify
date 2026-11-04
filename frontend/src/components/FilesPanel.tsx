import { Upload } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { errorMessage } from '../errors'
import type { WorkspaceData } from '../workspace'
import ConfirmDialog from './ConfirmDialog'
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
  const [removing, setRemoving] = useState<string | null>(null)

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
    await api.removeFile(projectId, path)
    data.reload()
    onRemoved(path)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-1.5 border-b border-slate-100 p-2.5">
        <label className="flex h-9 cursor-pointer items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-800 hover:bg-slate-50 has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand-600">
          {busy ? <Spinner /> : <Upload aria-hidden className="h-4 w-4" />}
          Add files
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
        <p className="text-xs text-slate-600">
          Slide decks you can make accessible are shown in maroon. Select one to open it.
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
            onRemove={setRemoving}
          />
        ) : (
          <p className="p-4 text-sm text-slate-500">{data.error ?? 'Loading files…'}</p>
        )}
      </div>
      {removing && (
        <ConfirmDialog
          title="Remove file?"
          confirmLabel="Remove file"
          onClose={() => setRemoving(null)}
          onConfirm={() => remove(removing)}
        >
          <span className="font-mono">{removing}</span> will be removed from this project.
        </ConfirmDialog>
      )}
    </div>
  )
}
