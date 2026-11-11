import type { FileVersion, Run } from './types'

// Where one saved version of a file came from, in plain words
export function versionSource(version: FileVersion): string {
  if (version.source === 'update') {
    return version.run_effort ? `Made accessible (${version.run_effort} effort)` : 'Made accessible'
  }
  if (version.source === 'restore') {
    return version.restored_from ? `Restored from version ${version.restored_from}` : 'Restored'
  }
  return 'Uploaded'
}

export interface VersionNotice {
  tone: 'success' | 'info' | 'warning'
  text: string
}

// What a finished run did with its file, so the person knows what the next run starts from
export function versionNotice(run: Run): VersionNotice | null {
  const name = run.main_file.split('/').pop() ?? run.main_file
  const started = run.input_version
  switch (run.version_outcome) {
    case 'saved':
      return {
        tone: 'success',
        text: `Saved as version ${run.output_version ?? ''} of ${name}. Running it again starts from this version, so edits you upload are kept.`,
      }
    case 'saved_not_current':
      return {
        tone: 'warning',
        text: `Saved as version ${run.output_version ?? ''}, but ${name} changed while this ran, so that change stays current. Use Version history to switch to this result.`,
      }
    case 'unchanged':
      return {
        tone: 'info',
        text: `Nothing needed changing, so ${name} stays at version ${started ?? ''}.`,
      }
    case 'not_saved':
      return {
        tone: 'warning',
        text: `This result failed a final check, so it was not saved. ${name} stays at version ${started ?? ''}.`,
      }
    default:
      return null
  }
}
