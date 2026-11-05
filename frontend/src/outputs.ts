export type OutputKind = 'deck' | 'pdf' | 'changes' | 'archive' | 'report' | 'other'

// What kind of file a download is, from its path in the run
export function outputKind(path: string): OutputKind {
  const lower = path.toLowerCase()
  if (lower.endsWith('.pptx')) return 'deck'
  if (lower.endsWith('.pdf')) return 'pdf'
  if (lower.endsWith('.diff')) return 'changes'
  if (lower.endsWith('.zip')) return 'archive'
  if (lower.endsWith('.html')) return 'report'
  return 'other'
}

const HINTS: Record<OutputKind, string | null> = {
  deck: 'Keep editing in PowerPoint',
  pdf: 'Tagged for screen readers, ready to share',
  changes: 'Every description and fix, slide by slide',
  archive: 'All the updated source files',
  report: 'The full accessibility report',
  other: null,
}

// One line under each download saying when to choose it
export function outputHint(path: string): string | null {
  return HINTS[outputKind(path)]
}
