import { Sparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { useUser } from '../authContext'
import { errorMessage } from '../errors'
import type { DefaultEffort } from '../types'
import EffortPicker from './EffortPicker'
import Modal from './Modal'
import { Alert, Button } from './ui'

interface Props {
  projectId: string
  count: number
  onStarted: () => void
  onClose: () => void
}

// Make every deck and document in a project accessible in one go, each as its own run
export default function MakeAllDialog({ projectId, count, onStarted, onClose }: Props) {
  const { preferences } = useUser()
  const [effort, setEffort] = useState<DefaultEffort>(preferences.default_effort)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function start() {
    setBusy(true)
    setError(null)
    try {
      await api.createRunsForAll(projectId, { effort })
      onStarted()
      onClose()
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <Modal title="Make all files accessible" onClose={onClose}>
      <div className="space-y-5 px-6 pb-6 pt-4">
        <p className="text-sm text-slate-700">
          All {count} files in this project will be made accessible, one run each. Files you ran before reuse their
          earlier descriptions, so you pay only for what changed.
        </p>
        <EffortPicker value={effort} onChange={setEffort} compact />
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={busy}
            onClick={() => void start()}
            icon={<Sparkles aria-hidden className="h-4 w-4" />}
          >
            Make {count} files accessible
          </Button>
        </div>
      </div>
    </Modal>
  )
}
