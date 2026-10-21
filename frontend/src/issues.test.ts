import { describe, expect, it } from 'vitest'
import { describeIssue, groupIssues, issueWhere, severityWord } from './issues'
import type { ReviewIssue } from './types'

const issue = (code: string, severity: string, extra: Partial<ReviewIssue> = {}): ReviewIssue => ({
  code,
  severity,
  message: `raw message for ${code}`,
  element_id: null,
  ...extra,
})

describe('describeIssue', () => {
  it('replaces technical wording with plain language', () => {
    const wording = describeIssue(
      issue('broken_mcid_link', 'error', { message: 'Page 3 MCID 3 lacks exactly one ParentTree owner' }),
    )
    expect(wording.title).not.toMatch(/MCID|ParentTree/)
    expect(wording.explanation).toMatch(/screen reader/i)
  })

  it('falls back to the original message for unknown codes', () => {
    const wording = describeIssue(issue('something_new', 'warning', { message: 'Something odd happened' }))
    expect(wording.title).toBe('Something odd happened')
  })
})

describe('issueWhere', () => {
  it('reads pages and quoted labels from the details', () => {
    expect(issueWhere(issue('unmarked_content', 'warning', { details: { page: 7 } }))).toBe('Page 7')
    expect(issueWhere(issue('contradicts_source', 'veto', { details: { quoted_label: 'Fold 3' } }))).toBe(
      'mentions “Fold 3”',
    )
    expect(issueWhere(issue('alt_missing', 'error'))).toBeNull()
  })
})

describe('groupIssues', () => {
  it('collapses repeats into one group with the worst severity first', () => {
    const groups = groupIssues([
      issue('unmarked_content', 'warning'),
      issue('broken_mcid_link', 'error'),
      issue('broken_mcid_link', 'error'),
      issue('visual_change', 'veto'),
      issue('unmarked_content', 'warning'),
      issue('unmarked_content', 'warning'),
    ])
    expect(groups.map((group) => [group.code, group.issues.length])).toEqual([
      ['visual_change', 1],
      ['broken_mcid_link', 2],
      ['unmarked_content', 3],
    ])
  })

  it('labels severities in words', () => {
    expect(severityWord('error')).toBe('Problem')
    expect(severityWord('veto')).toBe('Blocked')
    expect(severityWord('info')).toBe('Note')
  })
})
