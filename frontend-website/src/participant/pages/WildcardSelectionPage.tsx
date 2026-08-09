import { useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import type { WildcardProblem } from '../types'
import Modal from '../components/Modal'
import { Button, Card, PageHeading } from '../components/ui'

export default function WildcardSelectionPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [problems, setProblems] = useState<WildcardProblem[]>([])
  const [selected, setSelected] = useState('')
  const [pendingChange, setPendingChange] = useState(false)
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => { void service.getWildcardProblems().then(setProblems) }, [service])

  const confirm = async () => {
    setWorking(true)
    setMessage('')
    try {
      await service.selectWildcardProblem(selected)
      await refresh()
      setPendingChange(false)
      setMessage('Replacement problem confirmed.')
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Problem selection failed.')
    } finally { setWorking(false) }
  }

  if (!dashboard) return null
  const permissions = getParticipantPermissions(dashboard)
  return (
    <div className="stack">
      <PageHeading eyebrow="Wildcard selection" title="Choose a replacement problem">The server verifies winner eligibility and availability when you confirm.</PageHeading>
      <div className="problem-grid">
        {problems.map((item) => (
          <label key={item.id} className={`card selectable ${selected === item.id ? 'is-selected' : ''}`}>
            <input type="radio" name="problem" checked={selected === item.id} onChange={() => setSelected(item.id)} disabled={!permissions.canSelectWildcardProblem} />
            <span><small>Problem #{String(item.number).padStart(2, '0')}</small><strong>{item.title}</strong><small>{item.summary}</small></span>
          </label>
        ))}
      </div>
      <Card className="action-row">
        <Button onClick={() => setPendingChange(true)} disabled={!permissions.canSelectWildcardProblem || !selected}>Choose replacement problem</Button>
        {!permissions.canSelectWildcardProblem && <p className="notice">Only your team leader can choose the replacement problem. All available options remain visible in spectator mode.</p>}
      </Card>
      {message && <p className={message.includes('confirmed') ? 'success' : 'error'} role="status">{message}</p>}
      <Modal open={pendingChange} onClose={() => setPendingChange(false)} title="Change problem?">
        <div className="problem-swap"><div><span className="problem-swap__tag">Current</span><strong>{dashboard.currentProblem?.title ?? '—'}</strong></div><span className="problem-swap__arrow">→</span><div><span className="problem-swap__tag">New</span><strong>{problems.find((problem) => problem.id === selected)?.title ?? '—'}</strong></div></div>
        <div className="modal__actions"><Button variant="secondary" onClick={() => setPendingChange(false)}>Cancel</Button><Button variant="gold" onClick={() => void confirm()} disabled={working}>{working ? 'Confirming…' : 'Confirm change'}</Button></div>
      </Modal>
    </div>
  )
}
