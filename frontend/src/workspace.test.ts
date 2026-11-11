import { describe, expect, it } from 'vitest'
import { latestRunsByFile } from './workspace'
import type { Run } from './types'

const run = (id: string, file: string, created: string): Run => ({
  id,
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
  input_version: null,
  output_version: null,
  version_outcome: '',
})

describe('latestRunsByFile', () => {
  it('keeps the newest run for each file', () => {
    const latest = latestRunsByFile([
      run('old', 'a.tex', '2026-10-01T10:00:00Z'),
      run('new', 'a.tex', '2026-10-02T10:00:00Z'),
      run('other', 'b.tex', '2026-10-01T09:00:00Z'),
    ])
    expect(latest.get('a.tex')?.id).toBe('new')
    expect(latest.get('b.tex')?.id).toBe('other')
    expect(latest.size).toBe(2)
  })

  it('ignores runs without a file', () => {
    expect(latestRunsByFile([run('x', '', '2026-10-01T10:00:00Z')]).size).toBe(0)
  })
})
