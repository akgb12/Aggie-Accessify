import { ChevronRight, FolderOpen, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, PROJECTS_CHANGED_EVENT } from '../api'
import ConfirmDialog from '../components/ConfirmDialog'
import Modal from '../components/Modal'
import { TextField } from '../components/fields'
import { Alert, Button, Card, EmptyState, PageHeader, Skeleton } from '../components/ui'
import { errorMessage } from '../errors'
import { relativeTime } from '../format'
import type { Project } from '../types'

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<Project | null>(null)
  const [renaming, setRenaming] = useState<Project | null>(null)

  useEffect(() => {
    const load = () =>
      api
        .listProjects()
        .then(setProjects)
        .catch((e) => setError(errorMessage(e)))
    void load()
    window.addEventListener(PROJECTS_CHANGED_EVENT, load)
    return () => window.removeEventListener(PROJECTS_CHANGED_EVENT, load)
  }, [])

  async function create(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    try {
      const project = await api.createProject(name.trim())
      setProjects((current) => [project, ...(current ?? [])])
      setName('')
      setError(null)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setCreating(false)
    }
  }

  async function remove(project: Project) {
    await api.deleteProject(project.id)
    setProjects((current) => (current ?? []).filter((item) => item.id !== project.id))
  }

  async function rename(project: Project, name: string) {
    const updated = await api.renameProject(project.id, name)
    setProjects((current) => (current ?? []).map((item) => (item.id === project.id ? updated : item)))
  }

  return (
    <div>
      <PageHeader
        title="Projects"
        subtitle="Upload Beamer slides and get back accessible LaTeX, a tagged PDF and a review report."
      />

      <Card className="mb-6">
        <form onSubmit={create} className="flex flex-wrap items-end gap-3">
          <label className="min-w-64 flex-1 text-sm font-medium text-slate-700">
            New project name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. CSCE 421 Lecture 1"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm placeholder:text-slate-400"
            />
          </label>
          <Button
            type="submit"
            variant="primary"
            loading={creating}
            disabled={!name.trim()}
            icon={<Plus aria-hidden className="h-4 w-4" />}
          >
            Create project
          </Button>
        </form>
      </Card>

      {error && (
        <div className="mb-4">
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        </div>
      )}

      {projects === null && !error && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((key) => (
            <Skeleton key={key} className="h-24" />
          ))}
        </div>
      )}

      {projects?.length === 0 && (
        <EmptyState icon={<FolderOpen aria-hidden className="h-6 w-6" />} title="No projects yet">
          Create your first project above, then upload a .zip of your Beamer slides.
        </EmptyState>
      )}

      {projects && projects.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <li
              key={project.id}
              className="group relative rounded-xl border border-slate-200 bg-white shadow-sm transition hover:border-brand-300 hover:shadow-md"
            >
              <Link to={`/projects/${project.id}`} className="flex items-center gap-4 rounded-xl p-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                  <FolderOpen aria-hidden className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-slate-900">{project.name}</span>
                  <span className="block text-sm text-slate-500">
                    {project.files.length} {project.files.length === 1 ? 'file' : 'files'} · updated{' '}
                    {relativeTime(project.updated_at)}
                  </span>
                </span>
                <ChevronRight aria-hidden className="h-5 w-5 text-slate-300 group-hover:text-brand-600" />
              </Link>
              <div className="absolute right-2 top-2 flex opacity-0 transition focus-within:opacity-100 group-hover:opacity-100">
                <button
                  type="button"
                  onClick={() => setRenaming(project)}
                  aria-label={`Rename ${project.name}`}
                  className="rounded-md p-1.5 text-slate-300 hover:bg-slate-100 hover:text-slate-700"
                >
                  <Pencil aria-hidden className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setDeleting(project)}
                  aria-label={`Delete ${project.name}`}
                  className="rounded-md p-1.5 text-slate-300 hover:bg-red-50 hover:text-red-600"
                >
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {deleting && (
        <ConfirmDialog
          title="Delete project?"
          confirmLabel="Delete project"
          onClose={() => setDeleting(null)}
          onConfirm={() => remove(deleting)}
        >
          “{deleting.name}” and all of its files and translations will be removed. This cannot be
          undone.
        </ConfirmDialog>
      )}
      {renaming && (
        <RenameDialog
          project={renaming}
          onClose={() => setRenaming(null)}
          onSave={(name) => rename(renaming, name)}
        />
      )}
    </div>
  )
}

function RenameDialog({
  project,
  onClose,
  onSave,
}: {
  project: Project
  onClose: () => void
  onSave: (name: string) => Promise<void>
}) {
  const [name, setName] = useState(project.name)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      await onSave(name.trim())
      onClose()
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <Modal title="Rename project" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4 px-5 pb-5 pt-3">
        <TextField label="Project name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={!name.trim() || name.trim() === project.name}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  )
}
