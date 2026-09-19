import { useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import type { Problem, WildcardProblem } from '../types'
import Countdown from '../components/Countdown'
import Modal from '../components/Modal'
import { Button, Card, PageHeading } from '../components/ui'

type Choice = 'ROUND1' | 'WILDCARD'

function ProblemChoiceCard({ label, problem, onChoose, disabled }: {
  label: string
  problem: Problem | WildcardProblem
  onChoose: () => void
  disabled: boolean
}) {
  return (
    <Card className="final-choice-card">
      <p className="eyebrow">{label}</p>
      <small>Problem #{String(problem.number).padStart(2, '0')}</small>
      <h2>{problem.title}</h2>
      <p>{problem.description}</p>
      <Button onClick={onChoose} disabled={disabled}>Use {label}</Button>
    </Card>
  )
}

export default function WildcardFinalChoicePage() {
  const { dashboard, service, refresh } = useParticipant()
  const [pendingChoice, setPendingChoice] = useState<Choice | null>(null)
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState('')
  if (!dashboard) return null

  const isWinner = dashboard.wildcard?.status === 'selected'
  const permissions = getParticipantPermissions(dashboard)
  const confirmed = Boolean(dashboard.finalProblemConfirmedAt)
  const choiceProblem = pendingChoice === 'ROUND1' ? dashboard.roundOneProblem : dashboard.wildcardProblem

  if (!isWinner || !dashboard.roundOneProblem || !dashboard.wildcardProblem) {
    return <div className="stack"><PageHeading eyebrow="Wildcard · Final choice" title="No final choice required" /><Card className="center-card"><p>Only qualified Wildcard winners with both problem assignments can confirm a final choice.</p></Card></div>
  }

  const confirm = async () => {
    if (!pendingChoice) return
    setWorking(true); setMessage('')
    try {
      await service.confirmFinalProblem(pendingChoice)
      setPendingChoice(null)
      await refresh()
      setMessage('Final problem confirmed.')
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Final problem choice failed.')
    } finally { setWorking(false) }
  }

  return (
    <div className="stack final-choice-page">
      <PageHeading eyebrow="Wildcard · Final choice" title="Choose the problem you will build">
        Compare both assignments carefully. Your selected Wildcard problem stays reserved even if you keep the Round 1 problem.
      </PageHeading>
      <Card className="final-choice-timer"><span>Choice closes in</span><Countdown timing={dashboard.timing} /></Card>
      <div className="final-choice-grid">
        <ProblemChoiceCard label="Round 1 Problem" problem={dashboard.roundOneProblem} onChoose={() => setPendingChoice('ROUND1')} disabled={!permissions.canConfirmFinalProblem || confirmed} />
        <ProblemChoiceCard label="Wildcard Problem" problem={dashboard.wildcardProblem} onChoose={() => setPendingChoice('WILDCARD')} disabled={!permissions.canConfirmFinalProblem || confirmed} />
      </div>
      {!permissions.isLeader && <p className="notice">Only your team leader can confirm the final problem.</p>}
      {confirmed && <p className="success">Your team confirmed the {dashboard.finalProblemChoice === 'ROUND1' ? 'Round 1' : 'Wildcard'} problem. Waiting for the other teams.</p>}
      {message && <p className={message.includes('confirmed') ? 'success' : 'error'} role="status">{message}</p>}
      <Modal open={pendingChoice !== null} onClose={() => !working && setPendingChoice(null)} title="Confirm final problem?">
        <p>You are choosing <strong>{choiceProblem?.title}</strong>.</p>
        <p className="notice">This choice is final and cannot be changed.</p>
        <div className="modal__actions"><Button variant="secondary" onClick={() => setPendingChoice(null)} disabled={working}>Cancel</Button><Button variant="gold" onClick={() => void confirm()} disabled={working}>{working ? 'Confirming…' : 'Confirm choice'}</Button></div>
      </Modal>
    </div>
  )
}
