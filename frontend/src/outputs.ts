export type OutputKind = 'deck' | 'document' | 'pdf' | 'changes' | 'archive' | 'report' | 'other'

// What kind of file a download is, from its path in the run
export function outputKind(path: string): OutputKind {
  const lower = path.toLowerCase()
  if (lower.endsWith('.pptx')) return 'deck'
  if (lower.endsWith('.docx')) return 'document'
  if (lower.endsWith('.pdf')) return 'pdf'
  if (lower.endsWith('.diff') || (lower.endsWith('.txt') && lower.includes('changes'))) return 'changes'
  if (lower.endsWith('.zip')) return 'archive'
  if (lower.endsWith('.html')) return 'report'
  return 'other'
}

const HINTS: Record<OutputKind, string | null> = {
  deck: 'Keep editing in PowerPoint',
  document: 'Keep editing in Word',
  pdf: 'Ready to share or post to Canvas',
  changes: 'Every description and fix, in order',
  archive: 'All the updated source files',
  report: 'The full accessibility report',
  other: null,
}

// One line under each download saying when to choose it
export function outputHint(path: string): string | null {
  return HINTS[outputKind(path)]
}
