export default function AdvanceButton({ label = 'Waiting for organizer' }: { label?: string; disabled?: boolean }) {
  return <p className="notice" role="status">{label} — controlled by the organizer.</p>
}
