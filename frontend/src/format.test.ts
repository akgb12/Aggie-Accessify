import { describe, expect, it } from 'vitest'
import {
  containerLabel,
  containerTitle,
  elementLabel,
  fileKind,
  formatBytes,
  formatCost,
  formatDuration,
  relativeTime,
  scoreTone,
  shortElementId,
} from './format'

describe('formatBytes', () => {
  it('scales units and trims digits', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(832851)).toBe('813 KB')
    expect(formatBytes(4377867)).toBe('4.2 MB')
  })

  it('rejects invalid input', () => {
    expect(formatBytes(-1)).toBe('–')
    expect(formatBytes(Number.NaN)).toBe('–')
  })
})

describe('relativeTime', () => {
  const now = Date.parse('2026-10-19T12:00:00Z')

  it('describes recent and older timestamps', () => {
    expect(relativeTime('2026-10-19T11:59:40Z', now)).toBe('just now')
    expect(relativeTime('2026-10-19T11:55:00Z', now)).toBe('5 minutes ago')
    expect(relativeTime('2026-10-19T09:00:00Z', now)).toBe('3 hours ago')
    expect(relativeTime('2026-10-17T12:00:00Z', now)).toBe('2 days ago')
  })

  it('handles invalid dates', () => {
    expect(relativeTime('not a date', now)).toBe('–')
  })
})

describe('formatDuration', () => {
  it('formats seconds and minutes', () => {
    expect(formatDuration(5_000)).toBe('5s')
    expect(formatDuration(72_000)).toBe('1m 12s')
    expect(formatDuration(-5)).toBe('0s')
  })
})

describe('formatCost', () => {
  it('formats zero, tiny and normal amounts', () => {
    expect(formatCost('0.000000')).toBe('$0.00')
    expect(formatCost('0.00421')).toBe('$0.0042')
    expect(formatCost(1.5)).toBe('$1.50')
    expect(formatCost('abc')).toBe('–')
  })
})

describe('scoreTone', () => {
  it('maps scores to tones', () => {
    expect(scoreTone(96.7)).toBe('success')
    expect(scoreTone(72)).toBe('warning')
    expect(scoreTone(43.3)).toBe('danger')
    expect(scoreTone(null)).toBe('warning')
  })
})

describe('fileKind and shortElementId', () => {
  it('classifies files', () => {
    expect(fileKind('Lecture1-Intro.tex')).toBe('tex')
    expect(fileKind('L02_Agent.pptx')).toBe('deck')
    expect(fileKind('Syllabus.DOCX')).toBe('document')
    expect(fileKind('Figures/takejob.PDF')).toBe('pdf')
    expect(fileKind('Figures/cnn.png')).toBe('image')
    expect(fileKind('comment.sty')).toBe('style')
    expect(fileKind('README')).toBe('other')
  })

  it('shortens element ids', () => {
    expect(shortElementId('slide_04/figure_01')).toBe('figure_01')
    expect(shortElementId('slide_01')).toBe('slide_01')
  })
})

describe('element wording', () => {
  it('turns container ids into readable names', () => {
    expect(containerLabel('slide_04')).toBe('Slide 4')
    expect(containerLabel('slide_12')).toBe('Slide 12')
  })

  it('uses the element text as the title and the place as the subtitle', () => {
    const label = elementLabel({
      id: 'slide_02/list_01/list_item_03',
      type: 'list_item',
      text: 'Grading: 40% exams',
    })
    expect(label.title).toBe('Grading: 40% exams')
    expect(label.subtitle).toBe('Slide 2 · List · Bullet')
  })

  it('falls back to the kind when there is no text and never exposes raw ids', () => {
    const label = elementLabel({
      id: 'slide_01/title_page_01/paragraph_03',
      type: 'paragraph',
      text: null,
    })
    expect(label.title).toBe('Text')
    expect(label.subtitle).toBe('Slide 1 · Title page')
    expect(`${label.title} ${label.subtitle}`).not.toMatch(/_\d/)
  })

  it('names Word headings, equations and the document outline plainly', () => {
    expect(elementLabel({ id: 'section_03/heading_01', type: 'heading', text: null }).title).toBe('Heading')
    expect(elementLabel({ id: 'slide_03/heading_01', type: 'heading', text: null }).title).toBe('Slide title')
    expect(elementLabel({ id: 'section_02/figure_01', type: 'figure', text: null, subtype: 'equation' }).title).toBe(
      'Equation',
    )
    const outline = elementLabel({ id: 'section_01/unknown_01', type: 'unknown', text: null, subtype: 'document_outline' })
    expect(outline.title).toBe('Document outline')
    expect(outline.subtitle).toBe('Section 1')
    // A plain line the outline step made a heading says its level
    const made = elementLabel({ id: 'section_02/paragraph_01', type: 'paragraph', text: '1. (24 pts)', role: 'H2' })
    expect(made.subtitle).toBe('Section 2 · Heading 2')
    // An equation with no text of its own is named by how it is read aloud
    const equation = elementLabel({ id: 'section_05/figure_02', type: 'figure', text: null, subtype: 'equation', alt: 'n sub 1 sine theta' })
    expect(equation.title).toBe('n sub 1 sine theta')
    expect(equation.subtitle).toBe('Section 5 · Equation')
  })

  it('titles a Word section only by a line that is a heading now', () => {
    const elements = new Map([
      ['section_02/paragraph_01', { type: 'paragraph', text: 'Equation 1', role: null }],
      ['section_03/paragraph_01', { type: 'paragraph', text: 'Guidelines:', role: 'H2' }],
      ['slide_01/title_01', { type: 'paragraph', text: 'Welcome', role: null }],
    ])
    expect(containerTitle({ id: 'section_02', title_element_id: 'section_02/paragraph_01' }, elements)).toBe('')
    expect(containerTitle({ id: 'section_03', title_element_id: 'section_03/paragraph_01' }, elements)).toBe('Guidelines:')
    expect(containerTitle({ id: 'slide_01', title_element_id: 'slide_01/title_01' }, elements)).toBe('Welcome')
  })

  it('shortens long text', () => {
    const label = elementLabel({ id: 'slide_01/paragraph_01', type: 'paragraph', text: 'word '.repeat(40) })
    expect(label.title.length).toBeLessThanOrEqual(70)
    expect(label.title.endsWith('…')).toBe(true)
  })
})
