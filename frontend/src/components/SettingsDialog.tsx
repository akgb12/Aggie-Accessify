import { Database, Gauge, SlidersHorizontal, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { formatUsd, fullName, passwordProblem } from '../account'
import { useAuth, useUser } from '../authContext'
import { errorMessage } from '../errors'
import type { DefaultEffort, Usage } from '../types'
import { cx } from './classes'
import ConfirmDialog from './ConfirmDialog'
import Modal from './Modal'
import { PasswordField, TextField } from './fields'
import { Alert, Button, Skeleton } from './ui'

export type SettingsTab = 'general' | 'account' | 'data' | 'usage'

const TABS: { id: SettingsTab; label: string; icon: ReactNode }[] = [
  { id: 'general', label: 'General', icon: <SlidersHorizontal aria-hidden className="h-4 w-4" /> },
  { id: 'account', label: 'Account', icon: <UserRound aria-hidden className="h-4 w-4" /> },
  { id: 'data', label: 'Data controls', icon: <Database aria-hidden className="h-4 w-4" /> },
  { id: 'usage', label: 'Usage', icon: <Gauge aria-hidden className="h-4 w-4" /> },
]

const EFFORTS: { value: DefaultEffort; label: string; hint: string }[] = [
  { value: 'low', label: 'Low', hint: 'Quick pass' },
  { value: 'medium', label: 'Medium', hint: 'Balanced' },
  { value: 'high', label: 'High', hint: 'Most thorough' },
]

export default function SettingsDialog({
  initialTab,
  onClose,
}: {
  initialTab: SettingsTab
  onClose: () => void
}) {
  const [tab, setTab] = useState<SettingsTab>(initialTab)
  return (
    <Modal title="Settings" onClose={onClose} bare className="max-w-3xl">
      <div className="flex h-[32rem] max-h-[calc(100vh-4rem)] flex-col sm:flex-row">
        <nav
          aria-label="Settings sections"
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 p-2 sm:w-52 sm:flex-col sm:border-b-0 sm:border-r"
        >
          <p className="hidden px-2.5 pb-2 pt-1 text-base font-semibold sm:block">Settings</p>
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={tab === item.id ? 'page' : undefined}
              onClick={() => setTab(item.id)}
              className={cx(
                'flex shrink-0 items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium',
                tab === item.id
                  ? 'bg-slate-100 text-slate-900'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
              )}
            >
              <span className="text-slate-400">{item.icon}</span>
              {item.label}
            </button>
          ))}
          <button
            type="button"
            onClick={onClose}
            className="ml-auto shrink-0 rounded-lg px-2.5 py-2 text-sm font-medium text-slate-500 hover:bg-slate-50 sm:ml-0 sm:mt-auto sm:text-left"
          >
            Close
          </button>
        </nav>
        <div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">
          {tab === 'general' && <General />}
          {tab === 'account' && <Account onClose={onClose} />}
          {tab === 'data' && <DataControls onClose={onClose} />}
          {tab === 'usage' && <UsageTab />}
        </div>
      </div>
    </Modal>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6 last:mb-0">
      <h3 className="text-lg font-semibold">{title}</h3>
      <div className="mt-3 divide-y divide-slate-100">{children}</div>
    </section>
  )
}

function Row({
  label,
  description,
  children,
}: {
  label: string
  description?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0 max-w-sm">
        <p className="text-sm font-medium text-slate-900">{label}</p>
        {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
      </div>
      {children}
    </div>
  )
}

function General() {
  const user = useUser()
  const { updateProfile } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const preferences = user.preferences

  async function save(patch: Partial<typeof preferences>) {
    setError(null)
    try {
      await updateProfile({ preferences: { ...preferences, ...patch } })
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <>
      <Section title="General">
        <Row label="Default effort" description="Used when you press Translate. You can still change it each time.">
          <div role="radiogroup" aria-label="Default effort" className="flex gap-1.5">
            {EFFORTS.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={preferences.default_effort === option.value}
                onClick={() => void save({ default_effort: option.value })}
                title={option.hint}
                className={cx(
                  'rounded-lg border px-3 py-1.5 text-sm font-medium',
                  preferences.default_effort === option.value
                    ? 'border-brand-600 bg-brand-50 text-brand-800 ring-1 ring-brand-600'
                    : 'border-slate-200 text-slate-700 hover:border-slate-300',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </Row>
        <Row
          label="Show demo options"
          description="Adds a field to Translate for forcing a weak first description, to watch the repair loop work."
        >
          <button
            type="button"
            role="switch"
            aria-checked={preferences.show_demo_options}
            aria-label="Show demo options"
            onClick={() => void save({ show_demo_options: !preferences.show_demo_options })}
            className={cx(
              'relative h-6 w-11 shrink-0 rounded-full transition-colors',
              preferences.show_demo_options ? 'bg-brand-700' : 'bg-slate-300',
            )}
          >
            <span
              aria-hidden
              className={cx(
                'absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform',
                preferences.show_demo_options && 'translate-x-5',
              )}
            />
          </button>
        </Row>
      </Section>
      {error && <Alert tone="danger">{error}</Alert>}
    </>
  )
}

function Account({ onClose }: { onClose: () => void }) {
  const user = useUser()
  const { updateProfile, signOut } = useAuth()
  const navigate = useNavigate()
  const [first, setFirst] = useState(user.first_name)
  const [last, setLast] = useState(user.last_name)
  const [nameMessage, setNameMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [pwMessage, setPwMessage] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  async function saveName(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setNameMessage(null)
    try {
      await updateProfile({ first_name: first, last_name: last })
      setNameMessage({ tone: 'success', text: 'Name saved.' })
    } catch (e) {
      setNameMessage({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setSaving(false)
    }
  }

  async function savePassword(event: React.FormEvent) {
    event.preventDefault()
    const problem = passwordProblem(next, confirm)
    if (problem) {
      setPwMessage({ tone: 'danger', text: problem })
      return
    }
    setSaving(true)
    setPwMessage(null)
    try {
      await api.changePassword(current, next, confirm)
      setCurrent('')
      setNext('')
      setConfirm('')
      setPwMessage({ tone: 'success', text: 'Password updated.' })
    } catch (e) {
      setPwMessage({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Section title="Account">
        <Row label="Username" description="Your TAMU username. It cannot be changed.">
          <span className="font-mono text-sm text-slate-700">{user.username}</span>
        </Row>
        <form onSubmit={saveName} className="space-y-3 py-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="First name" value={first} onChange={(e) => setFirst(e.target.value)} autoComplete="given-name" />
            <TextField label="Last name" value={last} onChange={(e) => setLast(e.target.value)} autoComplete="family-name" />
          </div>
          {nameMessage && <Alert tone={nameMessage.tone}>{nameMessage.text}</Alert>}
          <Button
            type="submit"
            loading={saving}
            disabled={!first.trim() || !last.trim() || (first === user.first_name && last === user.last_name)}
          >
            Save name
          </Button>
        </form>
        <Row label="Log out" description={`Signed in as ${fullName(user)}.`}>
          <Button
            onClick={() => {
              onClose()
              void signOut().then(() => navigate('/'))
            }}
          >
            Log out
          </Button>
        </Row>
      </Section>
      <Section title="Change password">
        <form onSubmit={savePassword} className="space-y-3 py-3">
          <PasswordField label="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
          <PasswordField label="New password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" hint="At least 10 characters." />
          <PasswordField label="Confirm new password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
          {pwMessage && <Alert tone={pwMessage.tone}>{pwMessage.text}</Alert>}
          <Button type="submit" loading={saving} disabled={!current || !next || !confirm}>
            Update password
          </Button>
        </form>
      </Section>
    </>
  )
}

function DataControls({ onClose }: { onClose: () => void }) {
  const { clearUser } = useAuth()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState<'projects' | 'account' | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  return (
    <>
      <Section title="Data controls">
        <Row
          label="Delete all projects"
          description="Removes every project, its files and all translations. Your account stays."
        >
          <Button variant="danger" className="border border-red-200" onClick={() => setDialog('projects')}>
            Delete all
          </Button>
        </Row>
        <Row
          label="Delete account"
          description="Permanently deletes your account and everything in it."
        >
          <Button variant="destructive" onClick={() => setDialog('account')}>
            Delete account
          </Button>
        </Row>
      </Section>
      {message && <Alert tone="success">{message}</Alert>}
      {dialog === 'projects' && (
        <ConfirmDialog
          title="Delete all projects?"
          confirmLabel="Delete all projects"
          typeToConfirm="delete"
          onClose={() => setDialog(null)}
          onConfirm={async () => {
            const result = await api.deleteAllProjects()
            setMessage(result.detail)
            navigate('/')
          }}
        >
          Every project you own, with its uploaded files and translations, will be removed. This
          cannot be undone.
        </ConfirmDialog>
      )}
      {dialog === 'account' && (
        <ConfirmDialog
          title="Delete your account?"
          confirmLabel="Delete my account"
          askPassword
          onClose={() => setDialog(null)}
          onConfirm={async (password) => {
            await api.deleteAccount(password)
            onClose()
            clearUser()
            navigate('/')
          }}
        >
          Your account, all of your projects and all of their translations will be permanently
          deleted. This cannot be undone.
        </ConfirmDialog>
      )}
    </>
  )
}

function UsageTab() {
  const [usage, setUsage] = useState<Usage | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .usage()
      .then(setUsage)
      .catch((e) => setError(errorMessage(e)))
  }, [])

  const stats = usage
    ? [
        ['Projects', String(usage.projects)],
        ['Translations', `${usage.succeeded_runs} of ${usage.runs} succeeded`],
        ['Spend this month', formatUsd(usage.cost_usd_this_month)],
        ['Spend, all time', formatUsd(usage.cost_usd)],
        ['Tokens in / out', `${usage.input_tokens.toLocaleString()} / ${usage.output_tokens.toLocaleString()}`],
      ]
    : []

  return (
    <Section title="Usage">
      {error && <Alert tone="danger">{error}</Alert>}
      {!usage && !error && <Skeleton className="h-40" />}
      {usage && (
        <dl className="divide-y divide-slate-100">
          {stats.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between py-3 text-sm">
              <dt className="text-slate-600">{label}</dt>
              <dd className="font-medium text-slate-900">{value}</dd>
            </div>
          ))}
          <div className="py-3 text-sm text-slate-500">
            Credits: not enabled yet. Spend is tracked here so a university budget can be tied to
            your account later.
          </div>
        </dl>
      )}
    </Section>
  )
}
