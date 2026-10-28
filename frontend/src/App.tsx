import { Accessibility, House } from 'lucide-react'
import { Link, Route, Routes } from 'react-router-dom'
import { useAuth } from './authContext'
import AccountMenu from './components/AccountMenu'
import { PageContainer, Skeleton } from './components/ui'
import EditorPage from './pages/EditorPage'
import LoginPage from './pages/LoginPage'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'
import RunRedirect from './pages/RunRedirect'

export default function App() {
  const { user, loading } = useAuth()
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="z-30 shrink-0 border-b border-slate-200 bg-white">
        <div className="flex h-12 items-center gap-1 px-4">
          <Link to="/" className="flex items-center gap-2.5 rounded-lg">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-800 text-white">
              <Accessibility aria-hidden className="h-4 w-4" />
            </span>
            <span className="text-sm font-semibold tracking-tight text-slate-900">
              Accessible Slides
            </span>
          </Link>
          {user && (
            <Link
              to="/"
              aria-label="All projects"
              title="All projects"
              className="ml-2 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              <House aria-hidden className="h-4 w-4" />
            </Link>
          )}
          {user && <AccountMenu />}
        </div>
      </header>
      <main id="content" className="min-h-0 flex-1 overflow-auto">
        {loading && (
          <PageContainer>
            <Skeleton className="h-40" />
          </PageContainer>
        )}
        {!loading && !user && <LoginPage />}
        {!loading && user && (
        <Routes>
          <Route
            path="/"
            element={
              <PageContainer>
                <ProjectsPage />
              </PageContainer>
            }
          />
          <Route
            path="/projects/:id"
            element={
              <PageContainer>
                <ProjectPage />
              </PageContainer>
            }
          />
          <Route path="/projects/:id/editor" element={<EditorPage />} />
          <Route path="/runs/:id" element={<RunRedirect />} />
          <Route
            path="*"
            element={
              <PageContainer>
                <p>Page not found.</p>
              </PageContainer>
            }
          />
        </Routes>
        )}
      </main>
    </div>
  )
}
