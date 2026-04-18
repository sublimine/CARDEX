import { useAuthContext } from '../auth/AuthContext'

export function useAuth() {
  return useAuthContext()
}
