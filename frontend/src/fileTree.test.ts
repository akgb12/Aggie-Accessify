import { describe, expect, it } from 'vitest'
import { buildTree, foldersAbove } from './fileTree'
import type { ProjectFile } from './types'

const file = (path: string): ProjectFile => ({
  id: 1,
  path,
  size: 1,
  sha256: '',
  uploaded_at: '',
  version: 1,
  versions: 1,
})

describe('buildTree', () => {
  it('nests folders and lists folders before files in natural order', () => {
    const tree = buildTree([
      file('Lecture10.tex'),
      file('Lecture2.tex'),
      file('Figures/b.png'),
      file('Figures/a.pdf'),
      file('comment.sty'),
    ])
    expect(tree.map((node) => node.name)).toEqual(['Figures', 'comment.sty', 'Lecture2.tex', 'Lecture10.tex'])
    expect(tree[0].folder).toBe(true)
    expect(tree[0].children.map((node) => node.path)).toEqual(['Figures/a.pdf', 'Figures/b.png'])
  })

  it('keeps the original file on leaves', () => {
    const tree = buildTree([file('a/b/c.tex')])
    expect(tree[0].children[0].children[0].file?.path).toBe('a/b/c.tex')
  })
})

describe('foldersAbove', () => {
  it('lists every parent folder', () => {
    expect(foldersAbove('a/b/c.tex')).toEqual(['a', 'a/b'])
    expect(foldersAbove('c.tex')).toEqual([])
  })
})
