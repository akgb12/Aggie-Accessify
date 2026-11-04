import { ChevronDown, LogOut, Settings } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fullName, initials } from '../account'
import { useAuth, useUser } from '../authContext'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/kit/dropdown-menu'
import type { SettingsTab } from './SettingsDialog'

const SettingsDialog = lazy(() => import('./SettingsDialog'))

// The signed-in person's menu: a Radix menu, so arrow keys, typeahead and focus return work
export default function AccountMenu() {
  const user = useUser()
  const { signOut } = useAuth()
  const navigate = useNavigate()
  const [settings, setSettings] = useState<SettingsTab | null>(null)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={`Account menu for ${fullName(user)}`}
          className="flex h-9 items-center gap-2 rounded-md pl-1 pr-2 text-sm font-semibold text-slate-800 hover:bg-slate-100 data-[state=open]:bg-slate-100"
        >
          <span
            aria-hidden
            className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-100 text-xs font-semibold text-slate-800 ring-1 ring-slate-200"
          >
            {initials(user)}
          </span>
          <span className="hidden max-w-40 truncate sm:block">{user.first_name}</span>
          <ChevronDown aria-hidden className="h-4 w-4 text-slate-500" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={6} className="w-64">
          <DropdownMenuLabel className="font-normal">
            <span className="block truncate text-sm font-semibold text-slate-900">{fullName(user)}</span>
            <span className="block truncate text-xs text-slate-600">{user.username}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setSettings('general')}>
            <Settings aria-hidden className="h-4 w-4" />
            Settings
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => void signOut().then(() => navigate('/'))}>
            <LogOut aria-hidden className="h-4 w-4" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {settings && (
        <Suspense fallback={null}>
          <SettingsDialog initialTab={settings} onClose={() => setSettings(null)} />
        </Suspense>
      )}
    </>
  )
}
