import { describe, expect, it } from 'vitest'
import type { FileVersion, Run } from './types'
import { versionNotice, versionSource } from './versions'

const version = (patch: Partial<FileVersion>): FileVersion => ({
  id: 'v',
  number: 1,
  source: 'upload',
  created_at: '2026-11-10T00:00:00Z',
  size: 1,
  current: false,
  run_id: null,
  run_effort: null,
  run_a_score: null,
  restored_from: null,
  ...patch,
})

const run = (patch: Partial<Run>): Run =>
  ({ main_file: 'decks/L05.pptx', input_version: 2, output_version: 3, version_outcome: 'saved', ...patch }) as Run

describe('versionSource', () => {
  it('says where each version came from', () => {
    expect(versionSource(version({}))).toBe('Uploaded')
    expect(versionSource(version({ source: 'update', run_effort: 'high' }))).toBe('Made accessible (high effort)')
    expect(versionSource(version({ source: 'restore', restored_from: 1 }))).toBe('Restored from version 1')
  })
})

describe('versionNotice', () => {
  it('names the version a run saved', () => {
    expect(versionNotice(run({}))?.text).toMatch(/^Saved as version 3 of L05\.pptx\./)
  })
  it('says the file stays put when nothing changed or a check failed', () => {
    expect(versionNotice(run({ version_outcome: 'unchanged', output_version: null }))?.text).toBe(
      'Nothing needed changing, so L05.pptx stays at version 2.',
    )
    expect(versionNotice(run({ version_outcome: 'not_saved' }))?.tone).toBe('warning')
  })
  it('says nothing for runs from before versions were kept', () => {
    expect(versionNotice(run({ version_outcome: '' }))).toBeNull()
  })
})
