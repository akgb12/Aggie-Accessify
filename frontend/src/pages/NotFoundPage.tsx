import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { buttonClasses } from '../components/classes'
import { EmptyState, PageContainer } from '../components/ui'
import { useDocumentTitle } from '../hooks'

export default function NotFoundPage() {
  useDocumentTitle('Page not found')
  return (
    <PageContainer>
      <h1 className="font-display-caps mb-6 text-3xl text-slate-900">Page not found</h1>
      <EmptyState
        icon={<Compass aria-hidden className="h-6 w-6" />}
        title="This address does not match a page"
        action={
          <Link to="/" className={buttonClasses('primary')}>
            Go to your projects
          </Link>
        }
      >
        The link may be out of date, or the project may have been deleted.
      </EmptyState>
    </PageContainer>
  )
}
