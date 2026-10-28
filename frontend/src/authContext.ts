import { createContext, useContext } from 'react'
import type { Preferences, Registration, User } from './types'

export interface AuthValue {
  user: User | null
  loading: boolean
  signIn: (username: string, password: string) => Promise<void>
  register: (body: Registration) => Promise<void>
  signOut: () => Promise<void>
  updateProfile: (patch: {
    first_name?: string
    last_name?: string
    preferences?: Preferences
  }) => Promise<void>
  clearUser: () => void
}

export const AuthContext = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

// For screens that only render once someone is signed in
export function useUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('No signed-in user')
  return user
}
