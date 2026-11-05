import { Accessibility } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cx } from './classes'

// Placeholder product mark until there is a real logo: the accessibility figure on maroon
export function BrandMark({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cx('flex shrink-0 items-center justify-center rounded-md bg-brand-800', className)}>
      <Accessibility className="h-3/5 w-3/5 text-white" strokeWidth={2} />
    </span>
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
