import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError, AUTH_EXPIRED_EVENT } from './api'
import { AuthContext } from './authContext'
import type { Preferences, Registration, User } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((error) => {
        // Not signed in is the normal first visit; anything else also leaves the sign-in page up
        if (!(error instanceof ApiError && error.status === 401)) console.error(error)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const expired = () => setUser(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, expired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expired)
  }, [])

  const signIn = useCallback(async (username: string, password: string) => {
    setUser(await api.login(username, password))
  }, [])
  const register = useCallback(async (body: Registration) => {
    setUser(await api.register(body))
  }, [])
  const signOut = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
    }
  }, [])
  const updateProfile = useCallback(
    async (patch: { first_name?: string; last_name?: string; preferences?: Preferences }) => {
      setUser(await api.updateProfile(patch))
    },
    [],
  )
  const clearUser = useCallback(() => setUser(null), [])

  const value = useMemo(
    () => ({ user, loading, signIn, register, signOut, updateProfile, clearUser }),
    [user, loading, signIn, register, signOut, updateProfile, clearUser],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
