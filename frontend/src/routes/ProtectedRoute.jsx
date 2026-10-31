import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { ShieldOff } from 'lucide-react'

import { useAuth } from '../context/AuthContext'
import { Button } from '../components/ui/Button'
import { PageLoader } from '../components/ui/Table'

/**
 * Gate a route on authentication, and optionally on role.
 *
 * This is a usability boundary, not the security boundary: the backend checks
 * the role on every endpoint, so a user who reached a page they should not see
 * would get 403s from the API regardless of what this component does.
 */
export function ProtectedRoute({ roles }) {
  const { isAuthenticated, initialising, role } = useAuth()
  const location = useLocation()

  // Wait for the stored token to be exchanged for a profile, so a hard refresh
  // does not bounce a signed-in user to the login screen.
  if (initialising) return <PageLoader label="Restoring your session" />

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (roles && !roles.includes(role)) {
    return <ForbiddenPage />
  }

  return <Outlet />
}

/** Shown when a signed-in user reaches a page their role cannot use. */
export function ForbiddenPage() {
  const { role } = useAuth()

  return (
    <div className="flex flex-col items-center px-6 py-20 text-center">
      <span className="rounded-full bg-amber-50 p-3.5 text-amber-600">
        <ShieldOff size={24} aria-hidden="true" />
      </span>
      <h1 className="mt-4 text-[19px] font-semibold text-navy-800">
        You do not have access to this page
      </h1>
      <p className="mt-2 max-w-md text-[13.5px] leading-relaxed text-slate-500">
        Your account is signed in as{' '}
        <span className="font-medium text-slate-700">{role}</span>, which does not have
        permission for this area. If you believe this is wrong, ask a sales manager to
        review your role.
      </p>
      <Button
        variant="secondary"
        className="mt-5"
        onClick={() => window.history.back()}
      >
        Go back
      </Button>
    </div>
  )
}

/** Keeps a signed-in user away from the login and registration screens. */
export function PublicOnlyRoute() {
  const { isAuthenticated, initialising } = useAuth()
  if (initialising) return <PageLoader label="Loading" />
  if (isAuthenticated) return <Navigate to="/dashboard" replace />
  return <Outlet />
}
