import { useState, type FormEvent } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import AdvanceButton from '../components/AdvanceButton'
import { Button, Card, PageHeading } from '../components/ui'

export default function SubmissionPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [url, setUrl] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [working, setWorking] = useState(false)
  if (!dashboard) return null
  const permissions = getParticipantPermissions(dashboard)
  const submitted = Boolean(dashboard.submission)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setWorking(true)
    setMessage(null)
    try {
      await service.submitGitHubRepository(url)
      await refresh()
      setMessage({ type: 'success', text: 'Repository submitted for judging.' })
      setUrl('')
    } catch (cause) {
      setMessage({ type: 'error', text: cause instanceof Error ? cause.message : 'Submission failed.' })
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="stack">
      <PageHeading eyebrow="Final submission" title={submitted ? 'Submission received' : 'Submit your repository'}>
        {dashboard.currentProblem?.title}
      </PageHeading>

      <Card>
        {submitted && dashboard.submission ? (
          <div className="submitted">
            <span className="confirmation-mark">✓</span>
            <h2>Repository locked in</h2>
            <a className="text-link" href={dashboard.submission.repositoryUrl} target="_blank" rel="noreferrer">{dashboard.submission.repositoryUrl}</a>
            <p className="muted">Submitted at {new Date(dashboard.submission.submittedAt).toLocaleString()}</p>
          </div>
        ) : (
          <form className="form" onSubmit={submit}>
            <label className={!permissions.canSubmitRepository ? 'is-locked' : ''}>
              <span>GitHub repository URL</span>
              <input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/team/project" disabled={!permissions.canSubmitRepository} required pattern="https://github.com/.*" title="Enter a valid GitHub repository URL" />
            </label>
            <Button type="submit" disabled={!permissions.canSubmitRepository || working}>{working ? 'Submitting…' : 'Submit repository'}</Button>
            {!permissions.canSubmitRepository && <p className="notice">Only your team leader can submit the final repository.</p>}
            {message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}
          </form>
        )}
      </Card>

      {submitted && <AdvanceButton label="Waiting for judging to begin" />}
    </div>
  )
}
