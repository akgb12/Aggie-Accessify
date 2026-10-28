import { LogOut, Settings } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fullName, initials } from '../account'
import { useAuth, useUser } from '../authContext'
import SettingsDialog from './SettingsDialog'
import type { SettingsTab } from './SettingsDialog'

export default function AccountMenu() {
  const user = useUser()
  const { signOut } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [settings, setSettings] = useState<SettingsTab | null>(null)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        button.current?.focus()
      }
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  const item =
    'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-slate-700 hover:bg-slate-100'

  return (
    <div ref={root} className="relative ml-auto">
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${fullName(user)}`}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 hover:bg-slate-100"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-800 text-xs font-semibold text-white">
          {initials(user)}
        </span>
        <span className="hidden max-w-40 truncate text-sm font-medium text-slate-700 sm:block">
          {user.first_name}
        </span>
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Account"
          className="absolute right-0 z-40 mt-1 w-64 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg"
        >
          <div className="px-2.5 py-2">
            <p className="truncate text-sm font-semibold text-slate-900">{fullName(user)}</p>
            <p className="truncate text-xs text-slate-500">{user.username}</p>
          </div>
          <div className="my-1 border-t border-slate-100" />
          <button
            type="button"
            role="menuitem"
            className={item}
            onClick={() => {
              setOpen(false)
              setSettings('general')
            }}
          >
            <Settings aria-hidden className="h-4 w-4 text-slate-400" />
            Settings
          </button>
          <button
            type="button"
            role="menuitem"
            className={item}
            onClick={() => {
              setOpen(false)
              void signOut().then(() => navigate('/'))
            }}
          >
            <LogOut aria-hidden className="h-4 w-4 text-slate-400" />
            Log out
          </button>
        </div>
      )}
      {settings && <SettingsDialog initialTab={settings} onClose={() => setSettings(null)} />}
    </div>
  )
}
