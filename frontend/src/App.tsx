import { Accessibility } from 'lucide-react'
import { Link, Route, Routes } from 'react-router-dom'
import { PageContainer } from './components/ui'
import ProjectPage from './pages/ProjectPage'
import ProjectsPage from './pages/ProjectsPage'
import RunPage from './pages/RunPage'

export default function App() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="z-30 shrink-0 border-b border-slate-200 bg-white">
        <div className="flex h-12 items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2.5 rounded-lg">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-800 text-white">
              <Accessibility aria-hidden className="h-4 w-4" />
            </span>
            <span className="text-sm font-semibold tracking-tight text-slate-900">
              Accessible Slides
            </span>
          </Link>
          <nav aria-label="Main">
            <Link
              to="/"
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Projects
            </Link>
          </nav>
        </div>
      </header>
      <main id="content" className="min-h-0 flex-1 overflow-auto">
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
          <Route path="/runs/:id" element={<RunPage />} />
          <Route
            path="*"
            element={
              <PageContainer>
                <p>Page not found.</p>
              </PageContainer>
            }
          />
        </Routes>
      </main>
    </div>
  )
}
