import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import * as authApi from '../api/auth'
import { setSessionExpiredHandler, tokenStore } from '../api/client'

const AuthContext = createContext(null)

export const ROLES = {
  CUSTOMER: 'CUSTOMER',
  SALES_EMPLOYEE: 'SALES_EMPLOYEE',
  SALES_MANAGER: 'SALES_MANAGER',
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [customer, setCustomer] = useState(null)
  // `initialising` covers the first profile fetch, so protected routes can wait
  // instead of bouncing a signed-in user to the login page on a hard refresh.
  const [initialising, setInitialising] = useState(Boolean(tokenStore.access))
  const [sessionExpired, setSessionExpired] = useState(false)

  const applyProfile = useCallback((profile) => {
    setUser(profile.user)
    setCustomer(profile.customer ?? null)
  }, [])

  const clearSession = useCallback(() => {
    authApi.logout()
    setUser(null)
    setCustomer(null)
  }, [])

  // A refresh that fails mid-session: drop the user to the login screen with an
  // explanation rather than letting requests fail silently.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null)
      setCustomer(null)
      setSessionExpired(true)
    })
  }, [])

  // Restore the session on first load if a token is in storage.
  useEffect(() => {
    let cancelled = false
    if (!tokenStore.access) {
      setInitialising(false)
      return () => {
        cancelled = true
      }
    }

    authApi
      .getProfile()
      .then((profile) => {
        if (!cancelled) applyProfile(profile)
      })
      .catch(() => {
        if (!cancelled) clearSession()
      })
      .finally(() => {
        if (!cancelled) setInitialising(false)
      })

    return () => {
      cancelled = true
    }
  }, [applyProfile, clearSession])

  const login = useCallback(
    async (email, password) => {
      setSessionExpired(false)
      const result = await authApi.login(email, password)
      // The login response carries the user; fetch the profile too so a
      // customer's linked record is available immediately.
      setUser(result.user)
      try {
        const profile = await authApi.getProfile()
        applyProfile(profile)
      } catch {
        /* The user is signed in; the customer record can load on demand. */
      }
      return result.user
    },
    [applyProfile]
  )

  const register = useCallback(
    async (payload) => {
      setSessionExpired(false)
      const result = await authApi.register(payload)
      setUser(result.user)
      try {
        const profile = await authApi.getProfile()
        applyProfile(profile)
      } catch {
        /* as above */
      }
      return result.user
    },
    [applyProfile]
  )

  const refreshProfile = useCallback(async () => {
    const profile = await authApi.getProfile()
    applyProfile(profile)
    return profile
  }, [applyProfile])

  const value = useMemo(() => {
    const role = user?.role ?? null
    return {
      user,
      customer,
      role,
      initialising,
      sessionExpired,
      isAuthenticated: Boolean(user),
      isCustomer: role === ROLES.CUSTOMER,
      isEmployee: role === ROLES.SALES_EMPLOYEE,
      isManager: role === ROLES.SALES_MANAGER,
      isStaff: role === ROLES.SALES_EMPLOYEE || role === ROLES.SALES_MANAGER,
      hasRole: (...roles) => Boolean(role) && roles.flat().includes(role),
      login,
      register,
      logout: clearSession,
      refreshProfile,
      clearSessionExpired: () => setSessionExpired(false),
    }
  }, [
    user,
    customer,
    initialising,
    sessionExpired,
    login,
    register,
    clearSession,
    refreshProfile,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside an AuthProvider')
  return context
}
