import type { ProjectFile } from './types'

export interface TreeNode {
  name: string
  path: string
  folder: boolean
  children: TreeNode[]
  file?: ProjectFile
}

const compare = (a: TreeNode, b: TreeNode) =>
  Number(b.folder) - Number(a.folder) || a.name.localeCompare(b.name, undefined, { numeric: true })

// Turn flat file paths like Figures/cnn.png into nested folders, folders first
export function buildTree(files: ProjectFile[]): TreeNode[] {
  const root: TreeNode = { name: '', path: '', folder: true, children: [] }
  for (const file of files) {
    const parts = file.path.split('/')
    let node = root
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join('/')
      const isFile = index === parts.length - 1
      let child = node.children.find((item) => item.name === part && item.folder === !isFile)
      if (!child) {
        child = { name: part, path, folder: !isFile, children: [], file: isFile ? file : undefined }
        node.children.push(child)
      }
      node = child
    })
  }
  const sort = (node: TreeNode) => {
    node.children.sort(compare)
    node.children.forEach(sort)
  }
  sort(root)
  return root.children
}

// Folders that must be open to show a file
export function foldersAbove(path: string): string[] {
  const parts = path.split('/')
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join('/'))
}
