# Document outline

A course document (a syllabus, handout, lab, worksheet or exam) is being made accessible. Screen-reader users move through a document by its headings, so every real heading must be marked as one, at the right level. Some lines in this document only look like headings: they are bold or larger but were typed as normal text.

You receive:
- lines: in reading order, every line that is already a heading (it has a level) and every line that looks like one (bold, points, capitals and centered say how it looks; page says where it is).
- opening_lines: the first lines of the document.
- foreign_runs: pieces of text marked as a language other than the document's language. The mark is often left over from a template or a copied paragraph.
- needs_title: whether the document lacks a title in its properties.

Decide:
1. headings: for each line without a level, give level 1 to 6 if it is a real heading, or 0 if it is not. A heading names the section that follows it, such as "Course Description", "Grading Policy", "Part 2: Procedure" or "Question 3". Lines that are not headings: a course code or subtitle on a title block (unless it is the document's main title), dates, names, a term such as "Summer 2024", labels inside a form, emphasised sentences, and answer lines. Use level 1 for the document's main title and for the top sections when there is no title; nest deeper levels under them by how the document is organised, following the look (bigger or capitalised lines are usually higher). Keep existing headings as they are and fit the new ones around them. Never skip a level going deeper.
2. english_runs: the run numbers in foreign_runs whose text is plainly English words, so the language mark is a mistake. Leave out text that is really in another language, such as a French quotation, a name or a term from another language.
3. title: when needs_title is true, a short title for the document's properties (at most 12 words), normally its main heading or the course and document name from the opening lines, written as the document writes it. Otherwise an empty string.

Never invent text. Return only the fields required by the provided output schema.
