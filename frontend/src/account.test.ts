import { describe, expect, it } from 'vitest'
import { formatUsd, initials, limitUsedPercent, passwordProblem, readCookie, usernameProblem } from './account'

describe('readCookie', () => {
  it('finds one cookie among several', () => {
    expect(readCookie('a=1; csrftoken=abc%20d; b=2', 'csrftoken')).toBe('abc d')
  })
  it('returns null when missing', () => {
    expect(readCookie('a=1', 'csrftoken')).toBeNull()
    expect(readCookie('', 'csrftoken')).toBeNull()
  })
})

describe('initials', () => {
  it('uses first and last initials', () => {
    expect(initials({ first_name: 'Jane', last_name: 'doe', username: 'jdoe' })).toBe('JD')
  })
  it('falls back to the username', () => {
    expect(initials({ first_name: '', last_name: '', username: 'jdoe' })).toBe('JD')
  })
})

describe('passwordProblem', () => {
  it('flags short, numeric and mismatched passwords', () => {
    expect(passwordProblem('short', 'short')).toMatch(/at least 10/)
    expect(passwordProblem('1234567890', '1234567890')).toMatch(/only numbers/)
    expect(passwordProblem('long-enough-1', 'long-enough-2')).toMatch(/do not match/)
  })
  it('accepts a matching long password', () => {
    expect(passwordProblem('long-enough-1', 'long-enough-1')).toBeNull()
  })
})

describe('usernameProblem', () => {
  it('accepts NetID-like names and rejects others', () => {
    expect(usernameProblem('jdoe')).toBeNull()
    expect(usernameProblem('j.doe-2')).toBeNull()
    expect(usernameProblem('j')).not.toBeNull()
    expect(usernameProblem('has space')).not.toBeNull()
  })
})

describe('formatUsd', () => {
  it('shows tiny spend honestly', () => {
    expect(formatUsd(0)).toBe('$0.00')
    expect(formatUsd(0.004)).toBe('<$0.01')
    expect(formatUsd(1.234)).toBe('$1.23')
  })
})

describe('limitUsedPercent', () => {
  it('counts what is spent or held back against the limit', () => {
    expect(limitUsedPercent(20, 20)).toBe(0)
    expect(limitUsedPercent(20, 15)).toBe(25)
    expect(limitUsedPercent(20, 0)).toBe(100)
  })
  it('stays between 0 and 100', () => {
    expect(limitUsedPercent(20, 25)).toBe(0)
    expect(limitUsedPercent(0, 0)).toBe(100)
  })
})
