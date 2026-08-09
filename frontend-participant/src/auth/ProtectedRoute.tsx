import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { authenticated } = useAuth()
  const location = useLocation()
  return authenticated ? children : <Navigate to="/login" replace state={{ from: location.pathname }} />
}
