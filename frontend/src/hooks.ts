import { useCallback, useEffect, useState } from 'react'

// A boolean preference remembered across visits; storage failures fall back to the default
export function usePersistentFlag(key: string, initial: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    try {
      const stored = window.localStorage.getItem(key)
      return stored === null ? initial : stored === '1'
    } catch {
      return initial
    }
  })
  const update = useCallback(
    (next: boolean) => {
      setValue(next)
      try {
        window.localStorage.setItem(key, next ? '1' : '0')
      } catch {
        // the preference simply is not remembered
      }
    },
    [key],
  )
  return [value, update]
}

// Name the browser tab after the page, as "Page · Aggie Accessify"
export function useDocumentTitle(page: string | null | undefined) {
  useEffect(() => {
    document.title = page ? `${page} · Aggie Accessify` : 'Aggie Accessify'
  }, [page])
}
