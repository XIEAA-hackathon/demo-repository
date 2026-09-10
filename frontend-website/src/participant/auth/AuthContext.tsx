import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { clearAccessToken, getAccessToken } from '../services/apiClient'
import * as authService from '../services/authService'

interface AuthContextValue {
  authenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(Boolean(getAccessToken()))
  const login = useCallback(async (email: string, password: string) => {
    await authService.login(email, password)
    setAuthenticated(true)
  }, [])
  const logout = useCallback(async () => {
    try {
      await authService.logout()
    } finally {
      setAuthenticated(Boolean(getAccessToken()))
    }
  }, [])

  useEffect(() => {
    const unauthorized = () => {
      clearAccessToken()
      setAuthenticated(false)
    }
    window.addEventListener('participant:unauthorized', unauthorized)
    return () => window.removeEventListener('participant:unauthorized', unauthorized)
  }, [])

  const value = useMemo(() => ({ authenticated, login, logout }), [authenticated, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider.')
  return value
}
