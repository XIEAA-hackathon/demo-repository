import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { clearAccessToken, getAccessToken } from '../services/apiClient'
import * as authService from '../services/authService'

interface AuthContextValue {
  authenticated: boolean
  checking: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false)
  const [checking, setChecking] = useState(Boolean(getAccessToken()))
  const login = useCallback(async (email: string, password: string) => {
    await authService.login(email, password)
    try {
      await authService.validateParticipantSession()
      setAuthenticated(true)
    } catch (error) {
      clearAccessToken()
      setAuthenticated(false)
      throw error
    }
  }, [])
  const logout = useCallback(async () => {
    try {
      await authService.logout()
    } finally {
      clearAccessToken()
      setAuthenticated(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    const unauthorized = () => {
      clearAccessToken()
      setAuthenticated(false)
      setChecking(false)
    }
    window.addEventListener('participant:unauthorized', unauthorized)

    if (getAccessToken()) {
      void authService.validateParticipantSession()
        .then(() => { if (active) setAuthenticated(true) })
        .catch(() => {
          clearAccessToken()
          if (active) setAuthenticated(false)
        })
        .finally(() => { if (active) setChecking(false) })
    } else {
      setChecking(false)
    }

    return () => {
      active = false
      window.removeEventListener('participant:unauthorized', unauthorized)
    }
  }, [])

  const value = useMemo(() => ({ authenticated, checking, login, logout }), [authenticated, checking, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider.')
  return value
}
