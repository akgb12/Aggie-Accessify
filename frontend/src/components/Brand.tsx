import { Link } from 'react-router-dom'
import { cx } from './classes'

// The product monogram: two A's for Aggie Accessify (not the university's trademarked box logo)
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 32 32" className={cx('shrink-0', className)}>
      <rect width="32" height="32" rx="6" fill="#500000" />
      <path
        fill="#fff"
        d="M9.6 8h3.2l4.4 16h-3.1l-1-3.8H8.5L7.5 24H4.4zm-.4 9.5h3.7L11 10.6zM21.6 8h3.2l4.4 16h-3.1l-1-3.8h-4.6l-1 3.8h-3.1zm-.4 9.5h3.7l-1.9-6.9z"
      />
    </svg>
  )
}

// The thin maroon university bar every Texas A&M site carries, linking to tamu.edu
export function UniversityBar() {
  return (
    <div className="bg-brand-800 text-white">
      <div className="flex h-8 items-center px-4 sm:px-6">
        <a
          href="https://www.tamu.edu"
          className="font-display-caps rounded-sm text-sm tracking-wide text-white outline-offset-2 hover:underline focus-visible:outline-white"
        >
          Texas A&amp;M University
        </a>
      </div>
    </div>
  )
}

export function ProductLink() {
  return (
    <Link to="/" className="flex items-center gap-2.5 rounded-md" aria-label="Aggie Accessify, all projects">
      <BrandMark className="h-8 w-8" />
      <span className="font-display-caps text-xl text-slate-900">Aggie Accessify</span>
    </Link>
  )
}
