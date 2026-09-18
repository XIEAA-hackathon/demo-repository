import { useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import Modal from '../components/Modal'
import WaitingState from '../components/WaitingState'
import { Button, Card, PageHeading } from '../components/ui'

export default function WildcardFinalChoicePage() {
  const { dashboard, service, refresh } = useParticipant()
  const [selected, setSelected] = useState<'ROUND1' | 'WILDCARD' | ''>('')
  const [pendingChange, setPendingChange] = useState(false)
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState('')

  if (!dashboard) return null
  const permissions = getParticipantPermissions(dashboard)
  const choiceOpen = dashboard.eventState === 'WILDCARD_FINAL_CHOICE'
  const confirmed = dashboard.finalProblemChoice
  const paid = dashboard.wildcardCoinsPaid ?? dashboard.wildcard?.winningBid ?? null

  const confirm = async () => {
    if (!selected) return
    setWorking(true)
    setMessage('')
    try {
      await service.confirmFinalProblemChoice(selected)
      await refresh()
      setPendingChange(false)
      setSelected('')
      setMessage('Final problem confirmed.')
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Final problem confirmation failed.')
    } finally { setWorking(false) }
  }

  if (confirmed && dashboard.finalProblem) {
    return (
      <div className="stack">
        <PageHeading eyebrow="Wildcard · Final problem" title="Final problem confirmed" />
        <Card className="center-card">
          <span className="confirmation-mark">✓</span>
          <h2>Problem #{String(dashboard.finalProblem.number).padStart(2, '0')}</h2>
          <p>{dashboard.finalProblem.title}</p>
          <p className="muted">{dashboard.finalProblem.description}</p>
          <p className="muted">Final choice: {confirmed === 'ROUND1' ? 'Round 1 problem' : 'Wildcard problem'}</p>
          {paid != null && <p className="muted">Wildcard slot cost: {paid} coins (already deducted).</p>}
        </Card>
      </div>
    )
  }

  if (!choiceOpen) {
    return (
      <div className="stack">
        <PageHeading eyebrow="Wildcard · Final problem" title="Final choice not open" />
        <Card className="center-card"><WaitingState text="The final problem choice opens after every Wildcard winner selects a Wildcard problem." /></Card>
      </div>
    )
  }

  if (!dashboard.roundOneProblem || !dashboard.wildcardProblem) {
    return (
      <div className="stack">
        <PageHeading eyebrow="Wildcard · Final problem" title="Choose your final problem" />
        <Card className="center-card"><WaitingState text="Loading both problems…" /></Card>
      </div>
    )
  }

  const options = [
    { choice: 'ROUND1' as const, tag: 'Round 1 problem', problem: dashboard.roundOneProblem },
    { choice: 'WILDCARD' as const, tag: 'Wildcard problem', problem: dashboard.wildcardProblem },
  ]

  return (
    <div className="stack">
      <PageHeading eyebrow="Wildcard · Final problem" title="Choose your final problem">
        Pick which problem your team will build on. This cannot be changed after confirmation.
      </PageHeading>
      {paid != null && (
        <Card className="center-card">
          <p><strong>Wildcard slot cost: {paid} coins — already deducted.</strong></p>
          <p className="muted">You already paid {paid} coins for your Wildcard slot. Your final problem choice does not change that cost.</p>
        </Card>
      )}
      <div className="problem-grid">
        {options.map((item) => (
          <label key={item.choice} className={`card selectable ${selected === item.choice ? 'is-selected' : ''}`}>
            <input type="radio" name="final-problem" checked={selected === item.choice} onChange={() => setSelected(item.choice)} disabled={!permissions.isLeader} />
            <span>
              <small>{item.tag}</small>
              <strong>Problem #{String(item.problem.number).padStart(2, '0')} · {item.problem.title}</strong>
              <small className="wildcard-problem-description">{item.problem.description}</small>
            </span>
          </label>
        ))}
      </div>
      <Card className="action-row">
        <Button onClick={() => setPendingChange(true)} disabled={!permissions.isLeader || !selected}>Confirm final problem</Button>
        {!permissions.isLeader && <p className="notice">Only your team leader can confirm the final problem. Teammates can view the choices.</p>}
      </Card>
      {message && <p className={message.includes('confirmed') ? 'success' : 'error'} role="status">{message}</p>}
      <Modal open={pendingChange} onClose={() => setPendingChange(false)} title="Confirm final problem?">
        <div className="problem-swap">
          <div><span className="problem-swap__tag">Choice</span><strong>{selected === 'ROUND1' ? 'Round 1 problem' : 'Wildcard problem'}</strong></div>
        </div>
        <p className="notice">This choice is irreversible. {selected === 'ROUND1' ? 'Your paid Wildcard slot stays paid — choosing Round 1 does not refund it.' : 'No additional payment is charged — your Wildcard slot is already paid.'}</p>
        <div className="modal__actions">
          <Button variant="secondary" onClick={() => setPendingChange(false)}>Cancel</Button>
          <Button variant="gold" onClick={() => void confirm()} disabled={working}>{working ? 'Confirming…' : 'Confirm final problem'}</Button>
        </div>
      </Modal>
    </div>
  )
}
