import { useState } from 'react'
import type { ReactNode } from 'react'
import { errorMessage } from '../errors'
import Modal from './Modal'
import { PasswordField, TextField } from './fields'
import { Alert, Button } from './ui'

// Asks before a destructive action. Optionally the person must type a word or their password.
export default function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onClose,
  typeToConfirm,
  askPassword = false,
}: {
  title: string
  children: ReactNode
  confirmLabel: string
  onConfirm: (password: string) => Promise<void>
  onClose: () => void
  typeToConfirm?: string
  askPassword?: boolean
}) {
  const [typed, setTyped] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ready =
    (!typeToConfirm || typed.trim().toLowerCase() === typeToConfirm.toLowerCase()) &&
    (!askPassword || password.length > 0)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      await onConfirm(password)
      onClose()
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="space-y-5 px-6 pb-6 pt-4">
        <div className="text-sm text-slate-700">{children}</div>
        {typeToConfirm && (
          <TextField
            label={`Type “${typeToConfirm}” to confirm`}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            autoComplete="off"
          />
        )}
        {askPassword && (
          <PasswordField
            label="Your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="destructive" loading={busy} disabled={!ready}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
