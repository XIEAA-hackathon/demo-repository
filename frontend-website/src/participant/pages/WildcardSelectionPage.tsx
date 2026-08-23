import { useEffect, useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import type { WildcardProblem } from '../types'
import Modal from '../components/Modal'
import WaitingState from '../components/WaitingState'
import { Button, Card, PageHeading } from '../components/ui'

export default function WildcardSelectionPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [problems, setProblems] = useState<WildcardProblem[]>([])
  const [selected, setSelected] = useState('')
  const [pendingChange, setPendingChange] = useState(false)
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState('')
  const [loadingProblems, setLoadingProblems] = useState(false)
  const [problemError, setProblemError] = useState('')
  const isTurn = Boolean(dashboard?.wildcard?.isSelectionTurn)
  const loadProblems = async () => {
    setLoadingProblems(true); setProblemError('')
    try { setProblems(await service.getWildcardProblems()) }
    catch (cause) { setProblemError(cause instanceof Error ? cause.message : 'Available problems could not be loaded.') }
    finally { setLoadingProblems(false) }
  }
  useEffect(() => {
    if (!isTurn) { setProblems([]); return }
    void loadProblems()
    // The active turn changes server-side; reloading once per turn avoids exposing
    // the problem bank to teams that are still waiting.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTurn, service])

  const confirm = async () => {
    setWorking(true)
    setMessage('')
    try {
      await service.selectWildcardProblem(selected)
      await refresh()
      setPendingChange(false)
      setMessage('Final problem confirmed.')
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Problem selection failed.')
    } finally { setWorking(false) }
  }

  if (!dashboard) return null
  const permissions = getParticipantPermissions(dashboard)
  const wildcard = dashboard.wildcard
  if (wildcard?.status === 'selected' && dashboard.wildcardProblem) return <div className="stack"><PageHeading eyebrow="Wildcard · Problem selection" title="Final problem confirmed" /><Card className="center-card"><span className="confirmation-mark">✓</span><h2>Problem #{String(dashboard.wildcardProblem.number).padStart(2, '0')}</h2><p>{dashboard.wildcardProblem.title}</p><p className="muted">{dashboard.wildcardProblem.description}</p></Card></div>
  if (wildcard?.status === 'eliminated') return <div className="stack"><PageHeading eyebrow="Wildcard · Result" title="Outside the qualifying slots" /><Card className="center-card"><p>Your slot bid did not finish in the top {wildcard.slotCount ?? dashboard.gameConfig.wildcardSlots}.</p></Card></div>
  if (wildcard?.status !== 'qualified') return <div className="stack"><PageHeading eyebrow="Wildcard · Problem selection" title="Selection in progress" /><Card className="center-card"><WaitingState text="Qualified teams are selecting their problems in rank order." /></Card></div>
  if (!wildcard.isSelectionTurn) return <div className="stack"><PageHeading eyebrow={`Wildcard · Rank #${wildcard.rank}`} title="Your selection slot is secured" /><Card className="center-card"><h2>{wildcard.currentSelectionTeam ?? 'The next team'} is choosing now</h2><p>Your winning bid was {wildcard.winningBid} coins. Your team’s balance has been updated.</p><WaitingState text="Your problem choices will unlock when it is your turn." /></Card></div>
  return (
    <div className="stack">
      <PageHeading eyebrow={`Wildcard · Rank #${wildcard.rank}`} title="Choose your final problem">It is your turn. Once confirmed, the next ranked team can choose.</PageHeading>
      <div className="problem-grid">
        {problems.map((item) => (
          <label key={item.id} className={`card selectable ${selected === item.id ? 'is-selected' : ''}`}>
            <input type="radio" name="problem" checked={selected === item.id} onChange={() => setSelected(item.id)} disabled={!permissions.canSelectWildcardProblem || !wildcard.isSelectionTurn} />
            <span><small>Problem #{String(item.number).padStart(2, '0')}</small><strong>{item.title}</strong><small className="wildcard-problem-description">{item.description}</small></span>
          </label>
        ))}
      </div>
      {loadingProblems && <Card className="center-card"><WaitingState text="Loading remaining wildcard problems…" /></Card>}
      {!loadingProblems && problemError && <Card className="center-card"><p className="error" role="alert">{problemError}</p><Button variant="secondary" onClick={() => void loadProblems()}>Retry</Button></Card>}
      {!loadingProblems && !problemError && !problems.length && <Card className="center-card"><p className="notice">No available problems remain. Ask the organizer to verify the Wildcard problem bank.</p><Button variant="secondary" onClick={() => void loadProblems()}>Retry</Button></Card>}
      <Card className="action-row">
        <Button onClick={() => setPendingChange(true)} disabled={!permissions.canSelectWildcardProblem || !selected}>Choose final problem</Button>
        {!permissions.canSelectWildcardProblem && <p className="notice">Only your team leader can confirm the problem. Teammates can view the available choices.</p>}
      </Card>
      {message && <p className={message.includes('confirmed') ? 'success' : 'error'} role="status">{message}</p>}
      <Modal open={pendingChange} onClose={() => setPendingChange(false)} title="Confirm final problem?">
        <div className="problem-swap"><div><span className="problem-swap__tag">Round 1 history</span><strong>{dashboard.roundOneProblem?.title ?? 'No assignment'}</strong></div><span className="problem-swap__arrow">→</span><div><span className="problem-swap__tag">Final</span><strong>{problems.find((problem) => problem.id === selected)?.title ?? '—'}</strong></div></div>
        <p className="notice">This choice cannot be changed after confirmation.</p><div className="modal__actions"><Button variant="secondary" onClick={() => setPendingChange(false)}>Cancel</Button><Button variant="gold" onClick={() => void confirm()} disabled={working}>{working ? 'Confirming…' : 'Confirm problem'}</Button></div>
      </Modal>
    </div>
  )
}
