import { EllipsisVertical, FolderOpen, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, PROJECTS_CHANGED_EVENT } from '../api'
import ConfirmDialog from '../components/ConfirmDialog'
import Modal from '../components/Modal'
import { TextField } from '../components/fields'
import { Alert, Button, EmptyState, PageHeader, Skeleton } from '../components/ui'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/kit/dropdown-menu'
import { errorMessage } from '../errors'
import { relativeTime } from '../format'
import { useDocumentTitle } from '../hooks'
import type { Project } from '../types'

function fileCount(project: Project): string {
  const count = project.files.length
  if (count === 0) return 'No files yet'
  return `${count} ${count === 1 ? 'file' : 'files'}`
}

export default function ProjectsPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<Project | null>(null)
  const [renaming, setRenaming] = useState<Project | null>(null)
  useDocumentTitle('Projects')

  useEffect(() => {
    const load = () =>
      api
        .listProjects()
        .then((list) => {
          setProjects(list)
          setError(null)
        })
        .catch((e) => setError(errorMessage(e)))
    void load()
    window.addEventListener(PROJECTS_CHANGED_EVENT, load)
    return () => window.removeEventListener(PROJECTS_CHANGED_EVENT, load)
  }, [])

  async function create(name: string) {
    const project = await api.createProject(name)
    navigate(`/projects/${project.id}`)
  }

  async function remove(project: Project) {
    await api.deleteProject(project.id)
    setProjects((current) => (current ?? []).filter((item) => item.id !== project.id))
  }

  async function rename(project: Project, name: string) {
    const updated = await api.renameProject(project.id, name)
    setProjects((current) => (current ?? []).map((item) => (item.id === project.id ? updated : item)))
  }

  const newProject = (
    <Button variant="primary" icon={<Plus aria-hidden className="h-4 w-4" />} onClick={() => setCreating(true)}>
      New project
    </Button>
  )

  return (
    <div>
      <PageHeader
        display
        title="Projects"
        subtitle="Each project holds the slides for one lecture or course. Upload a PowerPoint deck or LaTeX Beamer slides, then make them accessible."
        actions={projects && projects.length > 0 ? newProject : undefined}
      />

      {error && (
        <div className="mb-6">
          <Alert tone="danger" title="Your projects could not be loaded">
            {error} Refresh the page to try again.
          </Alert>
        </div>
      )}

      {projects === null && !error && (
        <div aria-hidden className="divide-y divide-slate-200 rounded-lg border border-slate-200">
          {[0, 1, 2].map((key) => (
            <div key={key} className="flex items-center gap-4 px-4 py-4">
              <Skeleton className="h-4 w-64" />
              <Skeleton className="ml-auto h-4 w-24" />
            </div>
          ))}
        </div>
      )}

      {projects?.length === 0 && (
        <EmptyState
          icon={<FolderOpen aria-hidden className="h-6 w-6" />}
          title="Create your first project"
          action={newProject}
        >
          A project holds the slides for one lecture. You will upload a .pptx deck or a .zip of your Beamer
          slides next.
        </EmptyState>
      )}

      {projects && projects.length > 0 && (
        <div className="rounded-lg border border-slate-200">
          <div className="hidden grid-cols-[1fr_8rem_9rem_2.5rem] gap-4 border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-700 sm:grid">
            <span>Name</span>
            <span>Files</span>
            <span>Updated</span>
            <span className="sr-only">Actions</span>
          </div>
          <ul className="divide-y divide-slate-200">
            {projects.map((project) => (
              <li
                key={project.id}
                className="relative grid grid-cols-[1fr_2.5rem] items-center gap-x-4 px-4 py-3 transition-colors hover:bg-slate-50 sm:grid-cols-[1fr_8rem_9rem_2.5rem]"
              >
                <div className="min-w-0">
                  <Link
                    to={`/projects/${project.id}`}
                    className="block truncate font-semibold text-slate-900 underline-offset-4 after:absolute after:inset-0 hover:underline"
                  >
                    {project.name}
                  </Link>
                  <span className="block text-sm text-slate-600 sm:hidden">
                    {fileCount(project)} · updated {relativeTime(project.updated_at)}
                  </span>
                </div>
                <span className="hidden text-sm text-slate-600 sm:block">{fileCount(project)}</span>
                <span className="hidden text-sm text-slate-600 sm:block">{relativeTime(project.updated_at)}</span>
                <DropdownMenu>
                  <DropdownMenuTrigger
                    aria-label={`More actions for ${project.name}`}
                    className="relative z-10 flex h-9 w-9 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900 data-[state=open]:bg-slate-100"
                  >
                    <EllipsisVertical aria-hidden className="h-4 w-4" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-44">
                    <DropdownMenuItem onSelect={() => setRenaming(project)}>
                      <Pencil aria-hidden className="h-4 w-4" />
                      Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(project)}>
                      <Trash2 aria-hidden className="h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </li>
            ))}
          </ul>
        </div>
      )}

      {creating && (
        <NameDialog
          title="New project"
          label="Project name"
          placeholder="CSCE 625 Lecture 5: Graph search"
          confirmLabel="Create project"
          initial=""
          onClose={() => setCreating(false)}
          onSave={create}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Delete this project?"
          confirmLabel="Delete project"
          onClose={() => setDeleting(null)}
          onConfirm={() => remove(deleting)}
        >
          “{deleting.name}”, its uploaded files and every accessible version made from them will be removed. This cannot be
          undone.
        </ConfirmDialog>
      )}
      {renaming && (
        <NameDialog
          title="Rename project"
          label="Project name"
          confirmLabel="Save name"
          initial={renaming.name}
          onClose={() => setRenaming(null)}
          onSave={(name) => rename(renaming, name)}
        />
      )}
    </div>
  )
}

function NameDialog({
  title,
  label,
  placeholder,
  confirmLabel,
  initial,
  onClose,
  onSave,
}: {
  title: string
  label: string
  placeholder?: string
  confirmLabel: string
  initial: string
  onClose: () => void
  onSave: (name: string) => Promise<void>
}) {
  const [name, setName] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setError('Enter a name for the project.')
      return
    }
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
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="space-y-5 px-6 pb-6 pt-4" noValidate>
        <TextField
          label={label}
          value={name}
          placeholder={placeholder}
          onChange={(e) => setName(e.target.value)}
          error={error}
          autoFocus
        />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={busy} disabled={name.trim() === initial && initial !== ''}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
