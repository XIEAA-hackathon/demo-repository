export const LOGIN_PENDING_LABEL = 'Logging in…'
export const AUTHENTICATION_BUSY_MESSAGE = 'Authentication is busy. Please wait a moment and try again.'

export function participantLoginErrorMessage(status: number, message: string): string {
  if (status === 401) return 'Invalid username/email or password.'
  if (status === 403 && message === 'Participant access required') return 'Participant access required.'
  if (status === 502 || status === 503) return AUTHENTICATION_BUSY_MESSAGE
  return message
}
