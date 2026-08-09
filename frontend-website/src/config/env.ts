const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '')

export const PARTICIPANT_URL = trimTrailingSlash(
  import.meta.env.VITE_PARTICIPANT_URL || '/participant',
)

export const participantLoginUrl = `${PARTICIPANT_URL}/login`
