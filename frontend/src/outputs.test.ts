import { describe, expect, it } from 'vitest'
import { outputHint, outputKind } from './outputs'

describe('outputKind', () => {
  it('tells the deck, the PDF and the list of changes apart', () => {
    expect(outputKind('output/updated.pptx')).toBe('deck')
    expect(outputKind('output/tagged.pdf')).toBe('pdf')
    expect(outputKind('output/changes.diff')).toBe('changes')
    expect(outputKind('output/updated_project.zip')).toBe('archive')
    expect(outputKind('report.html')).toBe('report')
    expect(outputKind('output/notes.txt')).toBe('other')
  })
})

describe('outputHint', () => {
  it('says when to choose each download', () => {
    expect(outputHint('output/tagged.pdf')).toBe('Tagged for screen readers, ready to share')
    expect(outputHint('output/notes.txt')).toBeNull()
  })
})
