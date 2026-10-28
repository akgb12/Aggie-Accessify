import { readCookie } from './account'
import type {
  Preferences,
  Preflight,
  Project,
  Registration,
  Review,
  Run,
  RunCreate,
  Usage,
  User,
} from './types'

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const AUTH_EXPIRED_EVENT = 'auth:expired'
export const PROJECTS_CHANGED_EVENT = 'projects:changed'

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

async function csrfToken(): Promise<string> {
  // The session cookie needs a matching token on every write; fetch one if none is set yet
  let token = readCookie(document.cookie, 'csrftoken')
  if (!token) {
    await fetch(`${BASE_URL}/auth/csrf`, { credentials: 'include' })
    token = readCookie(document.cookie, 'csrftoken')
  }
  return token ?? ''
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!SAFE_METHODS.has((init.method ?? 'GET').toUpperCase())) {
    headers.set('X-CSRFToken', await csrfToken())
  }
  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers, credentials: 'include' })
  if (!response.ok) {
    // A 401 on data calls means the session ended; sign-in and register report their own errors
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    }
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // keep the status text when the body is not JSON
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function json(body: unknown, method = 'POST'): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export function artifactUrl(runId: string, relativePath: string): string {
  return `${BASE_URL}/runs/${runId}/artifact/${relativePath}`
}

// Page image URLs from the backend are absolute paths such as /api/runs/<id>/artifact/pages/...
export function absoluteUrl(path: string): string {
  const origin = new URL(BASE_URL).origin
  return path.startsWith('http') ? path : `${origin}${path}`
}

function encodePath(path: string): string {
  return path.split('/').map(encodeURIComponent).join('/')
}

export const api = {
  me: () => request<User>('/auth/me'),
  login: (username: string, password: string) =>
    request<User>('/auth/login', json({ username, password })),
  register: (body: Registration) => request<User>('/auth/register', json(body)),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  updateProfile: (patch: {
    first_name?: string
    last_name?: string
    preferences?: Preferences
  }) => request<User>('/auth/me', json(patch, 'PATCH')),
  changePassword: (current_password: string, new_password: string, confirm_password: string) =>
    request<{ detail: string }>(
      '/auth/password',
      json({ current_password, new_password, confirm_password }),
    ),
  usage: () => request<Usage>('/auth/usage'),
  deleteAllProjects: async () => {
    const result = await request<{ detail: string }>('/auth/projects', { method: 'DELETE' })
    window.dispatchEvent(new Event(PROJECTS_CHANGED_EVENT))
    return result
  },
  deleteAccount: (password: string) =>
    request<{ detail: string }>('/auth/delete', json({ password })),
  renameProject: (id: string, name: string) =>
    request<Project>(`/projects/${id}`, json({ name }, 'PATCH')),
  listProjects: () => request<Project[]>('/projects'),
  createProject: (name: string) => request<Project>('/projects', json({ name })),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  uploadFiles: (id: string, files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<Project>(`/projects/${id}/upload`, { method: 'POST', body: form })
  },
  putFile: (id: string, path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Project>(`/projects/${id}/files/${encodePath(path)}`, {
      method: 'PUT',
      body: form,
    })
  },
  removeFile: (id: string, path: string) =>
    request<Project>(`/projects/${id}/files/${encodePath(path)}`, { method: 'DELETE' }),
  preflight: (id: string, mainFile?: string | null) => {
    const query = mainFile ? `?main_file=${encodeURIComponent(mainFile)}` : ''
    return request<Preflight>(`/projects/${id}/preflight${query}`)
  },
  targets: (id: string) => request<{ candidates: string[] }>(`/projects/${id}/targets`),
  listRuns: (id: string) => request<Run[]>(`/projects/${id}/runs`),
  createRun: (id: string, payload: RunCreate) =>
    request<Run>(`/projects/${id}/runs`, json(payload)),
  getRun: (id: string) => request<Run>(`/runs/${id}`),
  getReview: (id: string) => request<Review>(`/runs/${id}/review`),
}
