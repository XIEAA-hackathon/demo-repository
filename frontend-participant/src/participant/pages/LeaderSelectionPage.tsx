import { useState } from 'react'
import { useParticipant } from '../ParticipantContext'
import AdvanceButton from '../components/AdvanceButton'
import Modal from '../components/Modal'
import { Avatar, Button, Card, PageHeading } from '../components/ui'

export default function LeaderSelectionPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [selected, setSelected] = useState(dashboard?.team.leaderId ?? '')
  const [confirming, setConfirming] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [working, setWorking] = useState(false)
  if (!dashboard) return null

  const currentLeaderId = dashboard.team.leaderId

  const save = async () => {
    setWorking(true)
    setMessage(null)
    try {
      await service.selectTeamLeader(selected)
      await refresh()
      setConfirming(false)
      setMessage({ type: 'success', text: 'Team leader confirmed.' })
    } catch (cause) {
      setMessage({ type: 'error', text: cause instanceof Error ? cause.message : 'Leader could not be selected.' })
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="stack">
      <PageHeading eyebrow="Team setup" title="Select your team leader">
        Only the team leader can place bids, make wildcard decisions, and submit the final GitHub repository.
      </PageHeading>

      <div className="leader-pick">
        {dashboard.team.members.map((member) => {
          const isLeader = currentLeaderId === member.id
          const isSelected = selected === member.id
          return (
            <button
              type="button"
              key={member.id}
              className={`card leader-card${isSelected ? ' is-selected' : ''}${isLeader ? ' is-leader' : ''}`}
              onClick={() => !isLeader && setSelected(member.id)}
              aria-pressed={isSelected}
              disabled={isLeader}
            >
              <span className="leader-card__avatar"><Avatar name={member.name} size="lg" />{isLeader && <span className="leader-card__crown">👑</span>}</span>
              <span className="leader-card__name">{member.name}</span>
              <span className="leader-card__email">{member.email}</span>
              {isLeader && <span className="leader-card__badge">Team leader</span>}
              {isSelected && !isLeader && <span className="leader-card__pick">Selected candidate</span>}
            </button>
          )
        })}
      </div>

      {message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}

      <Card className="action-row">
        <Button disabled={!selected || working} onClick={() => setConfirming(true)}>{working ? 'Confirming…' : 'Confirm leader'}</Button>
        <AdvanceButton label="Continue to problem preview" disabled={!currentLeaderId} />
      </Card>

      <Modal open={confirming} onClose={() => setConfirming(false)} title="Confirm team leader">
        <p className="muted">Make <strong>{dashboard.team.members.find((m) => m.id === selected)?.name}</strong> the sole team leader?</p>
        <div className="modal__actions">
          <Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
          <Button variant="gold" onClick={() => void save()} disabled={working}>{working ? 'Saving…' : 'Confirm leader'}</Button>
        </div>
      </Modal>
    </div>
  )
}