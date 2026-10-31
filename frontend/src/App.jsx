import { Navigate, Route, Routes } from 'react-router-dom'

import { ROLES } from './context/AuthContext'
import { AppShell } from './components/layout/AppShell'
import { ProtectedRoute, PublicOnlyRoute } from './routes/ProtectedRoute'

// Auth
import { Login } from './pages/auth/Login'
import { Register } from './pages/auth/Register'

// Shared
import { RoleDashboard } from './pages/common/RoleDashboard'
import { NotFound } from './pages/common/NotFound'
import { Notifications } from './pages/common/Notifications'
import { WorkflowHistory } from './pages/common/WorkflowHistory'
import { AuditLogs } from './pages/common/AuditLogs'
import { CompanySettings } from './pages/common/CompanySettings'
import { Profile } from './pages/common/Profile'
import { VerifyQuotation } from './pages/common/VerifyQuotation'
import { RequestDetail } from './pages/common/RequestDetail'
import { RequestList } from './pages/common/RequestList'
import { QuotationList } from './pages/common/QuotationList'
import { QuotationDetail } from './pages/common/QuotationDetail'

// Customer
import { ProductCatalogue } from './pages/customer/ProductCatalogue'
import { NewRequest } from './pages/customer/NewRequest'

// Staff
import { CustomerManagement } from './pages/staff/CustomerManagement'
import { CustomerDetail } from './pages/staff/CustomerDetail'
import { ProductManagement } from './pages/staff/ProductManagement'
import { MasterDataRequests } from './pages/staff/MasterDataRequests'
import { ExceptionManagement } from './pages/staff/ExceptionManagement'

// Manager
import { PendingApprovals } from './pages/manager/PendingApprovals'
import { ApprovalDetail } from './pages/manager/ApprovalDetail'
import { AnalyticsDashboard } from './pages/manager/AnalyticsDashboard'

const STAFF = [ROLES.SALES_EMPLOYEE, ROLES.SALES_MANAGER]
const MANAGER = [ROLES.SALES_MANAGER]
const CUSTOMER = [ROLES.CUSTOMER]

export function App() {
  return (
    <Routes>
      {/* ---- Public ---------------------------------------------------- */}
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
      </Route>

      {/* ---- Authenticated --------------------------------------------- */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<RoleDashboard />} />

          {/* Requests: one list and one detail page, scoped per role by the
              backend and by what each role is shown on screen. */}
          <Route path="/requests" element={<RequestList />} />
          <Route path="/requests/:id" element={<RequestDetail />} />

          {/* Quotations */}
          <Route path="/quotations" element={<QuotationList />} />
          <Route path="/quotations/:id" element={<QuotationDetail />} />

          {/* Everyone */}
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/verify" element={<VerifyQuotation />} />
          <Route path="/verify/:code" element={<VerifyQuotation />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<CompanySettings />} />

          {/* Customer only */}
          <Route element={<ProtectedRoute roles={CUSTOMER} />}>
            <Route path="/catalogue" element={<ProductCatalogue />} />
            <Route path="/requests/new" element={<NewRequest />} />
          </Route>

          {/* Sales staff */}
          <Route element={<ProtectedRoute roles={STAFF} />}>
            <Route path="/customers" element={<CustomerManagement />} />
            <Route path="/customers/:id" element={<CustomerDetail />} />
            <Route path="/products" element={<ProductManagement />} />
            {/* An employee proposes new master data here; a manager decides. */}
            <Route path="/master-data-requests" element={<MasterDataRequests />} />
            <Route path="/exceptions" element={<ExceptionManagement />} />
            <Route path="/approvals" element={<PendingApprovals />} />
            <Route path="/approvals/:id" element={<ApprovalDetail />} />
            <Route path="/workflow-history" element={<WorkflowHistory />} />
            {/* Staff can also raise a request on a customer's behalf. */}
            <Route path="/requests/new/for-customer" element={<NewRequest />} />
          </Route>

          {/* Manager only */}
          <Route element={<ProtectedRoute roles={MANAGER} />}>
            <Route path="/analytics" element={<AnalyticsDashboard />} />
            <Route path="/audit-logs" element={<AuditLogs />} />
          </Route>

          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>

      {/* A deep link hit while signed out lands on the login page, which then
          returns the user to where they were going. */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
