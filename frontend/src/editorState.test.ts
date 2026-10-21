import { describe, expect, it } from 'vitest'
import { editorPath, pickFile, whyNoTargets } from './editorState'
import type { ProjectFile, Run } from './types'

const run = (file: string, created: string): Run => ({
  id: `${file}-${created}`,
  project_id: 'p',
  status: 'succeeded',
  effort: 'medium',
  main_file: file,
  seed_weak: null,
  model_provider: 'fake',
  created_at: created,
  started_at: null,
  finished_at: null,
  storage_prefix: '',
  stop_reason: '',
  a_score: null,
  f_score: null,
  input_tokens: 0,
  output_tokens: 0,
  cost_usd: '0',
  error_message: '',
})

const file = (path: string): ProjectFile => ({ id: 1, path, size: 1, sha256: '', uploaded_at: '' })

describe('pickFile', () => {
  const targets = ['a.tex', 'b.tex', 'c.tex']

  it('uses the requested file when it is a presentation', () => {
    expect(pickFile('b.tex', targets, [])).toBe('b.tex')
  })

  it('ignores a request for something that is not a presentation', () => {
    expect(pickFile('notes.tex', targets, [])).toBeNull()
  })

  it('takes the only presentation without asking', () => {
    expect(pickFile(null, ['only.tex'], [])).toBe('only.tex')
  })

  it('falls back to the most recently translated file', () => {
    const runs = [run('a.tex', '2026-10-01T10:00:00Z'), run('c.tex', '2026-10-02T10:00:00Z')]
    expect(pickFile(null, targets, runs)).toBe('c.tex')
  })

  it('asks the user to choose when there are several and nothing was translated', () => {
    expect(pickFile(null, targets, [])).toBeNull()
  })
})

describe('whyNoTargets', () => {
  it('explains a project with only a PDF', () => {
    expect(whyNoTargets([file('slides.pdf')], [])).toBe('no_tex')
  })

  it('explains LaTeX that is not Beamer', () => {
    expect(whyNoTargets([file('notes.tex')], [])).toBe('no_beamer')
  })

  it('stays quiet when there is something to translate or nothing uploaded', () => {
    expect(whyNoTargets([file('a.tex')], ['a.tex'])).toBeNull()
    expect(whyNoTargets([], [])).toBeNull()
  })
})

describe('editorPath', () => {
  it('builds the editor address with the file and run', () => {
    expect(editorPath('p1', 'Lecture 1.tex', 'r9')).toBe('/projects/p1/editor?file=Lecture+1.tex&run=r9')
    expect(editorPath('p1', null)).toBe('/projects/p1/editor')
  })
})
