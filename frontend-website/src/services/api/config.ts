const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '')

export const API_URL = trimTrailingSlash(import.meta.env.VITE_API_URL || '/api')

const browserWebSocketUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`

export const WS_URL = trimTrailingSlash(
  import.meta.env.VITE_WS_URL
    || (API_URL.startsWith('/')
      ? browserWebSocketUrl
      : API_URL.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')),
)
