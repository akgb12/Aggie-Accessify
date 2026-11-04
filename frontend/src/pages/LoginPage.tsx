import { Info } from 'lucide-react'
import { useState } from 'react'
import { MIN_PASSWORD_LENGTH, passwordProblem, usernameProblem } from '../account'
import { useAuth } from '../authContext'
import { PasswordField, TextField } from '../components/fields'
import { Alert, Button } from '../components/ui'
import { Tabs, TabsList, TabsTrigger } from '@/components/kit/tabs'
import { errorMessage } from '../errors'
import { useDocumentTitle } from '../hooks'

type Mode = 'signin' | 'register'
type Field = 'firstName' | 'lastName' | 'username' | 'password' | 'confirm'
type Problems = Partial<Record<Field, string>>

const MISMATCH = 'The two passwords do not match.'

function findProblems(
  mode: Mode,
  values: { firstName: string; lastName: string; username: string; password: string; confirm: string },
): Problems {
  const problems: Problems = {}
  if (!values.username.trim()) problems.username = 'Enter your TAMU username.'
  if (!values.password) problems.password = 'Enter your password.'
  if (mode === 'signin') return problems
  if (!values.firstName.trim()) problems.firstName = 'Enter your first name.'
  if (!values.lastName.trim()) problems.lastName = 'Enter your last name.'
  if (values.username.trim()) {
    const username = usernameProblem(values.username)
    if (username) problems.username = username
  }
  if (values.password) {
    const password = passwordProblem(values.password, values.confirm)
    if (password === MISMATCH) problems.confirm = password
    else if (password) problems.password = password
  }
  return problems
}

export default function LoginPage() {
  const { signIn, register } = useAuth()
  const [mode, setMode] = useState<Mode>('signin')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [problems, setProblems] = useState<Problems>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useDocumentTitle(mode === 'signin' ? 'Sign in' : 'Create an account')

  function switchMode(next: string) {
    setMode(next as Mode)
    setError(null)
    setProblems({})
    setPassword('')
    setConfirm('')
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    const found = findProblems(mode, { firstName, lastName, username, password, confirm })
    setProblems(found)
    if (Object.keys(found).length > 0) return
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
    <div className="min-h-full bg-slate-50 px-4 py-12 sm:py-16">
      <div className="mx-auto w-full max-w-md">
        <h1 className="font-display-caps text-3xl text-slate-900">
          {mode === 'signin' ? 'Sign in' : 'Create an account'}
        </h1>
        <p className="mt-2 text-base text-slate-600">
          Aggie Accessify makes your course slides accessible. It describes figures, fixes titles and reading
          order, and gives you back the same deck.
        </p>

        <div className="mt-8 rounded-lg border border-slate-200 bg-white p-6 sm:p-8">
          <Tabs value={mode} onValueChange={switchMode} className="mb-6">
            <TabsList aria-label="Sign in or create an account" className="h-10 w-full rounded-md p-1">
              <TabsTrigger value="signin" className="rounded-sm font-semibold text-slate-600 data-[state=active]:text-slate-900 data-[state=active]:shadow-none data-[state=active]:ring-1 data-[state=active]:ring-slate-300">
                Sign in
              </TabsTrigger>
              <TabsTrigger value="register" className="rounded-sm font-semibold text-slate-600 data-[state=active]:text-slate-900 data-[state=active]:shadow-none data-[state=active]:ring-1 data-[state=active]:ring-slate-300">
                Create account
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <form onSubmit={submit} className="space-y-5" noValidate>
            {mode === 'register' && (
              <div className="grid gap-5 sm:grid-cols-2">
                <TextField
                  label="First name"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                  autoComplete="given-name"
                  error={problems.firstName}
                  required
                />
                <TextField
                  label="Last name"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                  autoComplete="family-name"
                  error={problems.lastName}
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
              error={problems.username}
              required
              autoFocus
            />
            <PasswordField
              label="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              hint={mode === 'register' ? `At least ${MIN_PASSWORD_LENGTH} characters.` : undefined}
              error={problems.password}
              required
            />
            {mode === 'register' && (
              <PasswordField
                label="Confirm password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                autoComplete="new-password"
                error={problems.confirm}
                required
              />
            )}
            {error && <Alert tone="danger">{error}</Alert>}
            <Button type="submit" variant="primary" className="h-10 w-full text-base" loading={busy}>
              {mode === 'signin' ? 'Sign in' : 'Create account'}
            </Button>
          </form>
        </div>

        <p className="mt-6 flex gap-2 text-sm text-slate-600">
          <Info aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Signing in with a password is temporary until Texas A&amp;M single sign on is connected. Do not reuse your NetID
            password here.
          </span>
        </p>
      </div>
    </div>
  )
}
