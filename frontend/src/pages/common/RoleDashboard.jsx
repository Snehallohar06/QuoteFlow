import { useAuth } from '../../context/AuthContext'
import { CustomerDashboard } from '../customer/CustomerDashboard'
import { SalesDashboard } from '../staff/SalesDashboard'
import { ManagerDashboard } from '../manager/ManagerDashboard'

/**
 * `/dashboard` renders a different page per role.
 *
 * One route keeps every post-login redirect and sidebar "Dashboard" link
 * pointing at the same place, whoever is signed in.
 */
export function RoleDashboard() {
  const { isCustomer, isManager } = useAuth()
  if (isCustomer) return <CustomerDashboard />
  if (isManager) return <ManagerDashboard />
  return <SalesDashboard />
}
