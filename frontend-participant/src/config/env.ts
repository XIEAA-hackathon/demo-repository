const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '')

export const API_URL = trimTrailingSlash(import.meta.env.VITE_API_URL || '/api')

const defaultWebSocketUrl = API_URL.startsWith('/')
  ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`
  : API_URL.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')

export const WS_URL = trimTrailingSlash(import.meta.env.VITE_WS_URL || defaultWebSocketUrl)
