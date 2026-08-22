import { useEffect, useState, type FormEvent } from 'react'
import { useParticipant } from '../ParticipantContext'
import { getParticipantPermissions } from '../permissions'
import AdvanceButton from '../components/AdvanceButton'
import { Button, Card, PageHeading } from '../components/ui'

export default function SubmissionPage() {
  const { dashboard, service, refresh } = useParticipant()
  const [url, setUrl] = useState('')
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [working, setWorking] = useState(false)
  useEffect(() => { setUrl(dashboard?.submission?.repositoryUrl ?? '') }, [dashboard?.submission?.repositoryUrl])
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
      setMessage({ type: 'success', text: dashboard.submission ? 'Repository URL updated.' : 'Repository submitted for judging.' })
    } catch (cause) {
      setMessage({ type: 'error', text: cause instanceof Error ? cause.message : 'Submission failed.' })
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="stack">
      <PageHeading eyebrow="Final submission" title={submitted ? 'Submission received' : 'Submit your repository'}>
        {dashboard.finalProblem ? `Problem #${String(dashboard.finalProblem.number).padStart(2, '0')} · ${dashboard.finalProblem.title}` : 'Your team needs a final problem before submitting.'}
      </PageHeading>

      <Card>
        {submitted && dashboard.submission && !dashboard.submissionsOpen ? (
          <div className="submitted">
            <span className="confirmation-mark">✓</span>
            <h2>Repository received</h2>
            <a className="text-link" href={dashboard.submission.repositoryUrl} target="_blank" rel="noreferrer">{dashboard.submission.repositoryUrl}</a>
            <p className="muted">Last updated {new Date(dashboard.submission.updatedAt || dashboard.submission.submittedAt).toLocaleString()}{dashboard.submission.submittedByName ? ` by ${dashboard.submission.submittedByName}` : ''}</p>
            <p className="notice">The submission window is closed. Your last saved URL remains on record.</p>
          </div>
        ) : (
          <form className="form" onSubmit={submit}>
            <label className={!permissions.canSubmitRepository ? 'is-locked' : ''}>
              <span>GitHub repository URL</span>
              <input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/team/project" disabled={!permissions.canSubmitRepository} required pattern="https://github.com/.*" title="Enter a valid GitHub repository URL" />
            </label>
            <Button type="submit" disabled={!permissions.canSubmitRepository || working || !dashboard.finalProblem}>{working ? 'Saving…' : submitted ? 'Update repository' : 'Submit repository'}</Button>
            {!dashboard.submissionsOpen && <p className="notice">The organizer has not opened submissions, or the window is now closed.</p>}
            {dashboard.submissionsOpen && !permissions.isLeader && <p className="notice">Only your team leader can submit or update the final repository.</p>}
            {submitted && dashboard.submission && <p className="muted">Last saved {new Date(dashboard.submission.updatedAt || dashboard.submission.submittedAt).toLocaleString()}</p>}
            {message && <p className={message.type === 'success' ? 'success' : 'error'} role="status">{message.text}</p>}
          </form>
        )}
      </Card>

      {submitted && <AdvanceButton label="Waiting for judging to begin" />}
    </div>
  )
}
