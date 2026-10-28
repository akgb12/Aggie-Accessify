import type { User } from './types'

export const MIN_PASSWORD_LENGTH = 10

export function readCookie(cookies: string, name: string): string | null {
  // Pull one value out of a document.cookie string
  for (const part of cookies.split(';')) {
    const [key, ...rest] = part.trim().split('=')
    if (key === name) return decodeURIComponent(rest.join('='))
  }
  return null
}

export function initials(user: Pick<User, 'first_name' | 'last_name' | 'username'>): string {
  const letters = `${user.first_name.trim()[0] ?? ''}${user.last_name.trim()[0] ?? ''}`
  return (letters || user.username.slice(0, 2)).toUpperCase()
}

export function fullName(user: Pick<User, 'first_name' | 'last_name'>): string {
  return `${user.first_name} ${user.last_name}`.trim()
}

// The server is the authority; this only saves a round trip for the obvious mistakes
export function passwordProblem(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${MIN_PASSWORD_LENGTH} characters.`
  }
  if (/^\d+$/.test(password)) return 'A password cannot be only numbers.'
  if (password !== confirm) return 'The two passwords do not match.'
  return null
}

export function usernameProblem(username: string): string | null {
  return /^[a-z0-9][a-z0-9._-]{2,31}$/i.test(username.trim())
    ? null
    : 'Use your TAMU username: 3 to 32 letters or numbers.'
}

export function formatUsd(value: number): string {
  return value > 0 && value < 0.01 ? '<$0.01' : `$${value.toFixed(2)}`
}
