import { Accessibility } from 'lucide-react'
import { useState } from 'react'
import { passwordProblem, usernameProblem } from '../account'
import { useAuth } from '../authContext'
import { cx } from '../components/classes'
import { PasswordField, TextField } from '../components/fields'
import { Alert, Button } from '../components/ui'
import { errorMessage } from '../errors'

type Mode = 'signin' | 'register'

export default function LoginPage() {
  const { signIn, register } = useAuth()
  const [mode, setMode] = useState<Mode>('signin')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setPassword('')
    setConfirm('')
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (mode === 'register') {
      const problem =
        usernameProblem(username) ??
        (!firstName.trim() || !lastName.trim() ? 'Enter your first and last name.' : null) ??
        passwordProblem(password, confirm)
      if (problem) {
        setError(problem)
        return
      }
    }
    setBusy(true)
    try {
      if (mode === 'signin') {
        await signIn(username, password)
      } else {
        await register({
          username,
          first_name: firstName,
          last_name: lastName,
          password,
          confirm_password: confirm,
        })
      }
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-800 text-white">
            <Accessibility aria-hidden className="h-6 w-6" />
          </span>
          <h1 className="mt-4 text-2xl font-bold tracking-tight">
            {mode === 'signin' ? 'Welcome back' : 'Create your account'}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Make your Beamer slides accessible. Sign in with your TAMU username.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div
            role="group"
            aria-label="Sign in or create an account"
            className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1 text-sm font-medium"
          >
            {(['signin', 'register'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                onClick={() => switchMode(value)}
                className={cx(
                  'rounded-md px-3 py-1.5',
                  mode === value
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800',
                )}
              >
                {value === 'signin' ? 'Sign in' : 'Create account'}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4" noValidate>
            {mode === 'register' && (
              <div className="grid grid-cols-2 gap-3">
                <TextField
                  label="First name"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                  autoComplete="given-name"
                  required
                />
                <TextField
                  label="Last name"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                  autoComplete="family-name"
                  required
                />
              </div>
            )}
            <TextField
              label="TAMU username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              required
              autoFocus
            />
            <PasswordField
              label="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              hint={mode === 'register' ? 'At least 10 characters.' : undefined}
              required
            />
            {mode === 'register' && (
              <PasswordField
                label="Confirm password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                autoComplete="new-password"
                required
              />
            )}
            {error && <Alert tone="danger">{error}</Alert>}
            <Button
              type="submit"
              variant="primary"
              className="w-full"
              loading={busy}
              disabled={!username || !password}
            >
              {mode === 'signin' ? 'Sign in' : 'Create account'}
            </Button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-slate-500">
          This is a temporary sign-in. Texas A&amp;M single sign-on will replace it.
          <br />
          Do not reuse your NetID password here.
        </p>
      </div>
    </div>
  )
}
