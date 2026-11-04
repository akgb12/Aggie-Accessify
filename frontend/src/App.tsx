import { lazy, Suspense } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './authContext'
import AccountMenu from './components/AccountMenu'
import { ProductLink, UniversityBar } from './components/Brand'
import { cx } from './components/classes'
import { PageContainer, Skeleton } from './components/ui'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'
import RunRedirect from './pages/RunRedirect'

// The editor is the largest page, so its code loads only when a project is opened
const EditorPage = lazy(() => import('./pages/EditorPage'))

function ProjectsNavLink() {
  // Projects stays current inside a project and its editor, since that is where they live
  const { pathname } = useLocation()
  const current = pathname === '/' || pathname.startsWith('/projects/')
  return (
    <NavLink
      to="/"
      aria-current={current ? 'page' : undefined}
      className={cx(
        'flex h-9 items-center rounded-md px-3 text-sm font-semibold',
        current ? 'bg-slate-100 text-slate-900' : 'text-slate-700 hover:bg-slate-100',
      )}
    >
      Projects
    </NavLink>
  )
}

export default function App() {
  const { user, loading } = useAuth()
  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-semibold"
      >
        Skip to content
      </a>
      <header className="z-30 shrink-0">
        <UniversityBar />
        <div className="flex h-14 items-center gap-6 border-b border-slate-200 bg-white px-4 sm:px-6">
          <ProductLink />
          {user && (
            <nav aria-label="Main" className="flex items-center gap-1">
              <ProjectsNavLink />
            </nav>
          )}
          {user && (
            <div className="ml-auto">
              <AccountMenu />
            </div>
          )}
        </div>
      </header>
      <main id="content" className="min-h-0 flex-1 overflow-auto">
        {loading && (
          <PageContainer>
            <Skeleton className="mb-8 h-9 w-56" />
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
            <Route path="/projects/:id" element={<ProjectPage />} />
            <Route
              path="/projects/:id/editor"
              element={
                <Suspense
                  fallback={
                    <div className="space-y-4 p-6">
                      <Skeleton className="h-10 w-72" />
                      <Skeleton className="h-56" />
                    </div>
                  }
                >
                  <EditorPage />
                </Suspense>
              }
            />
            <Route path="/runs/:id" element={<RunRedirect />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        )}
      </main>
    </div>
  )
}
