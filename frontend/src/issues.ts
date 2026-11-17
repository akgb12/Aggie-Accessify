import { severityRank } from './status'
import type { ReviewIssue } from './types'

export interface IssueWording {
  // Short name of the kind of issue
  title: string
  // One sentence a non-expert can act on
  explanation: string
}

const WORDING: Record<string, IssueWording> = {
  alt_missing: {
    title: 'Figure has no description',
    explanation: 'A screen reader has nothing to say for this figure yet.',
  },
  tagged_pdf_unavailable: {
    title: 'No PDF version was made',
    explanation: 'The accessible file is ready, but the PDF could not be exported from it.',
  },
  tagged_pdf_not_compliant: {
    title: 'PDF version needs a check',
    explanation: 'An automatic checker found parts of the PDF that do not fully meet the PDF/UA standard.',
  },
  alt_low_coverage: {
    title: 'Description leaves out visible labels',
    explanation: 'The description does not mention enough of the text shown in the figure.',
  },
  alt_length_outlier: {
    title: 'Description is very long',
    explanation: 'Short alt text is easier to listen to. Longer detail belongs in the extended description.',
  },
  alt_forbidden_opener: {
    title: 'Description starts with “Image of”',
    explanation: 'Screen readers already announce that it is an image, so this wording is redundant.',
  },
  alt_near_duplicate: {
    title: 'Description repeats nearby text',
    explanation: 'It says almost the same thing as the text next to the figure.',
  },
  alt_file_name: {
    title: 'Description looks like a file name',
    explanation: 'It should say what the figure shows, not what the file is called.',
  },
  contradicts_source: {
    title: 'Description does not match the figure',
    explanation: 'It mentions something that is not actually in the figure, or gets a count wrong.',
  },
  formula_changed: {
    title: 'An equation was altered',
    explanation: 'The equation no longer matches what you wrote, so the change was blocked.',
  },
  formula_alt_missing: {
    title: 'Equation has no readable text',
    explanation: 'A screen reader cannot read this equation aloud yet.',
  },
  visual_change: {
    title: 'The page looked different after tagging',
    explanation: 'Adding accessibility tags moved something on this page, so the change was blocked.',
  },
  unmarked_content: {
    title: 'Some text is not in the reading order',
    explanation: 'A screen reader may skip or misplace text that is not tagged. Decorative text is fine.',
  },
  broken_mcid_link: {
    title: 'Part of a page is not linked into the document structure',
    explanation: 'A screen reader may skip that part of the page.',
  },
  structure_content_missing: {
    title: 'Visible content is missing from the reading order',
    explanation: 'This content is on the page but is not part of the tagged structure.',
  },
  tag_marker_missing: {
    title: 'A tag could not be placed',
    explanation: 'The element exists but its tag could not be attached to the page.',
  },
  overlay_repeat_tagged: {
    title: 'Step-by-step slide repeats content',
    explanation: 'Slides that reveal content in steps repeat earlier content, and a screen reader may read it twice.',
  },
  overlay_marker_missing: {
    title: 'A step-by-step slide could not be tagged',
    explanation: 'One of the reveal steps has no tag, so it may be skipped.',
  },
  overlay_page_invalid: {
    title: 'A step-by-step slide points at the wrong page',
    explanation: 'The tag refers to a page that does not exist.',
  },
  not_handled: {
    title: 'Unsupported LaTeX',
    explanation: 'This part of your slides is passed through unchanged, because the tool does not understand it yet.',
  },
  missing_image: {
    title: 'Image file not found',
    explanation: 'The project refers to an image that was not uploaded, so a placeholder was used.',
  },
  coverage_unavailable: {
    title: 'Label check not possible',
    explanation: 'This figure was not drawn from source code, so its labels cannot be listed exactly and checked against the description.',
  },
  heading_level_skipped: {
    title: 'Heading skips a level',
    explanation: 'A heading jumps more than one level deeper than the one before it, which breaks the outline readers navigate by.',
  },
  vague_link_text: {
    title: 'Link text says nothing on its own',
    explanation: 'Words like "here" or "click here" do not say where a link goes when read out of context.',
  },
  capability_input_missing: {
    title: 'Figure could not be sent for description',
    explanation: 'The figure image was not available, so no description was requested.',
  },
  unmarked_fragile: {
    title: 'Slide left untagged (verbatim code)',
    explanation: 'Slides with verbatim code cannot be tagged safely and were left as they are.',
  },
  unmarked_recovered: {
    title: 'Slide left untagged',
    explanation: 'Tagging this slide broke compilation, so it was skipped. Your own source is fine.',
  },
  tex_errors_tolerated: {
    title: 'LaTeX reported small errors',
    explanation: 'The PDF was still produced, the same as on Overleaf.',
  },
  duplicate_title: {
    title: 'Slides share a title',
    explanation: 'Screen reader users jump between slides by title, so repeated titles look like one slide.',
  },
  low_contrast: {
    title: 'Text is hard to read against its background',
    explanation: 'The text color is too close to the background. Use a darker or lighter color.',
  },
  contrast_fixed: {
    title: 'Faint text was made readable',
    explanation:
      'Text too close to its background color now uses a darker or lighter shade of the same color, so it can be read.',
  },
  slide_missing_title: {
    title: 'Slide has no title',
    explanation: 'Screen reader users cannot find this slide in the slide list.',
  },
  title_not_first: {
    title: 'Title is not read first',
    explanation: 'Moving it automatically would change the slide, so reorder it in PowerPoint.',
  },
  reading_order_unclear: {
    title: 'Check the reading order',
    explanation:
      'This slide can be read in more than one order, so it was left as it is. Check it in PowerPoint under Arrange > Reading Order.',
  },
  layout_change_undone: {
    title: 'A fix was undone to keep the look unchanged',
    explanation: 'The change altered how a slide or page looks, so it was reversed. You can make it by hand.',
  },
  figure_image_unavailable: {
    title: 'Figure could not be shown to the describer',
    explanation: 'No picture of this figure could be made, so it was not described.',
  },
  table_header_unchecked: {
    title: 'Table header row not marked',
    explanation: 'The first row looks like a header. Turn on Header Row in PowerPoint if the look is fine.',
  },
  description_rejected: {
    title: 'A description was rejected',
    explanation: 'It quoted text that is not in the figure, so it was not used.',
  },
}

export function describeIssue(issue: ReviewIssue): IssueWording {
  return (
    WORDING[issue.code] ?? {
      title: issue.message.length > 70 ? `${issue.message.slice(0, 69)}…` : issue.message,
      explanation: issue.message,
    }
  )
}

export function severityWord(severity: string): string {
  switch (severity) {
    case 'error':
      return 'Problem'
    case 'veto':
      return 'Blocked'
    case 'warning':
      return 'Check'
    case 'info':
      return 'Note'
    default:
      return severity
  }
}

// Where an issue happened, in words a person can use: a page, or a count of items
export function issueWhere(issue: ReviewIssue): string | null {
  const page = issue.details?.page
  if (typeof page === 'number') return `Page ${page}`
  const quoted = issue.details?.quoted_label
  if (typeof quoted === 'string') return `mentions “${quoted}”`
  return null
}

export interface IssueGroup {
  code: string
  title: string
  explanation: string
  severity: string
  issues: ReviewIssue[]
}

// One group per kind of issue, worst first, so 65 identical errors read as one line
export function groupIssues(issues: ReviewIssue[]): IssueGroup[] {
  const groups = new Map<string, IssueGroup>()
  for (const issue of issues) {
    const wording = describeIssue(issue)
    const existing = groups.get(issue.code)
    if (existing) {
      existing.issues.push(issue)
      if (severityRank(issue.severity) < severityRank(existing.severity)) existing.severity = issue.severity
    } else {
      groups.set(issue.code, {
        code: issue.code,
        title: wording.title,
        explanation: wording.explanation,
        severity: issue.severity,
        issues: [issue],
      })
    }
  }
  return [...groups.values()].sort(
    (a, b) =>
      severityRank(a.severity) - severityRank(b.severity) || b.issues.length - a.issues.length,
  )
}
