import { useState } from 'react'
import { Building2, KeyRound, Mail, Shield, UserCog } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import * as authApi from '../../api/auth'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailList,
  DetailRow,
} from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Input, Select } from '../../components/ui/Field'
import { formatDateTime, formatMoney, initials } from '../../lib/format'
import {
  ROLE_LABELS,
  customerStatusInfo,
  tierInfo,
} from '../../lib/status'

export function Profile() {
  const { user, customer, role, isManager } = useAuth()
  const toast = useToast()

  const [passwords, setPasswords] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [passwordErrors, setPasswordErrors] = useState({})
  const [changing, setChanging] = useState(false)

  const [staff, setStaff] = useState({
    email: '',
    full_name: '',
    password: '',
    role: 'SALES_EMPLOYEE',
    phone: '',
  })
  const [staffErrors, setStaffErrors] = useState({})
  const [creating, setCreating] = useState(false)

  function validatePasswords() {
    const next = {}
    if (!passwords.current_password) next.current_password = 'Enter your current password.'
    if (!passwords.new_password) next.new_password = 'Choose a new password.'
    else if (passwords.new_password.length < 8)
      next.new_password = 'Use at least 8 characters.'
    else if (passwords.new_password === passwords.current_password)
      next.new_password = 'The new password must differ from the current one.'
    if (passwords.confirm_password !== passwords.new_password)
      next.confirm_password = 'The two passwords do not match.'
    setPasswordErrors(next)
    return Object.keys(next).length === 0
  }

  async function changePassword(event) {
    event.preventDefault()
    if (!validatePasswords()) return

    setChanging(true)
    try {
      await authApi.changePassword(
        passwords.current_password,
        passwords.new_password
      )
      toast.success(
        'Password changed',
        'Use the new password the next time you sign in.'
      )
      setPasswords({ current_password: '', new_password: '', confirm_password: '' })
      setPasswordErrors({})
    } catch (error) {
      if (error.isAuth) {
        setPasswordErrors({ current_password: 'That password is not correct.' })
      } else {
        toast.fromError(error, 'Could not change the password')
      }
    } finally {
      setChanging(false)
    }
  }

  function validateStaff() {
    const next = {}
    if (!staff.full_name.trim()) next.full_name = 'Enter their full name.'
    if (!staff.email.trim()) next.email = 'Enter an email address.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(staff.email.trim()))
      next.email = 'Enter a valid email address.'
    if (!staff.password) next.password = 'Set an initial password.'
    else if (staff.password.length < 8) next.password = 'Use at least 8 characters.'
    setStaffErrors(next)
    return Object.keys(next).length === 0
  }

  async function createStaff(event) {
    event.preventDefault()
    if (!validateStaff()) return

    setCreating(true)
    try {
      const created = await authApi.createStaffUser({
        email: staff.email.trim().toLowerCase(),
        full_name: staff.full_name.trim(),
        password: staff.password,
        role: staff.role,
        phone: staff.phone.trim() || undefined,
      })
      toast.success(
        'Account created',
        `${created.full_name} can now sign in as ${ROLE_LABELS[created.role]}.`
      )
      setStaff({
        email: '',
        full_name: '',
        password: '',
        role: 'SALES_EMPLOYEE',
        phone: '',
      })
      setStaffErrors({})
    } catch (error) {
      const fieldErrors = error.fieldErrors ?? {}
      if (Object.keys(fieldErrors).length > 0) setStaffErrors(fieldErrors)
      toast.fromError(error, 'Could not create the account')
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <PageHeader
        title="My profile"
        description="Your account, and the customer record it is linked to."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Account" icon={UserCog} />
          <CardBody>
            <div className="flex items-center gap-3">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-navy-700 text-[15px] font-semibold text-white">
                {initials(user?.full_name)}
              </span>
              <div className="min-w-0">
                <p className="text-[15px] font-semibold text-navy-800">
                  {user?.full_name}
                </p>
                <p className="flex items-center gap-1.5 text-[12.5px] text-slate-500">
                  <Mail size={12} aria-hidden="true" />
                  {user?.email}
                </p>
              </div>
            </div>

            <DetailList className="mt-4">
              <DetailRow
                label="Role"
                value={
                  <Badge tone="info" size="sm">
                    {ROLE_LABELS[role] ?? role}
                  </Badge>
                }
              />
              <DetailRow
                label="Account status"
                value={
                  <Badge tone={user?.status === 'ACTIVE' ? 'success' : 'danger'} size="sm">
                    {user?.status}
                  </Badge>
                }
              />
              {user?.phone ? <DetailRow label="Phone" value={user.phone} /> : null}
              <DetailRow label="Member since" value={formatDateTime(user?.created_at)} />
              <DetailRow
                label="Last sign-in"
                value={
                  user?.last_login_at ? formatDateTime(user.last_login_at) : 'This session'
                }
              />
            </DetailList>
          </CardBody>
        </Card>

        <Card id="password">
          <CardHeader
            title="Change password"
            description="You stay signed in on this device after changing it"
            icon={KeyRound}
          />
          <CardBody>
            <form onSubmit={changePassword} noValidate className="space-y-4">
              <Input
                label="Current password"
                type="password"
                autoComplete="current-password"
                value={passwords.current_password}
                error={passwordErrors.current_password}
                required
                onChange={(event) =>
                  setPasswords((current) => ({
                    ...current,
                    current_password: event.target.value,
                  }))
                }
              />
              <Input
                label="New password"
                type="password"
                autoComplete="new-password"
                value={passwords.new_password}
                error={passwordErrors.new_password}
                hint={passwordErrors.new_password ? undefined : 'At least 8 characters'}
                required
                onChange={(event) =>
                  setPasswords((current) => ({
                    ...current,
                    new_password: event.target.value,
                  }))
                }
              />
              <Input
                label="Confirm new password"
                type="password"
                autoComplete="new-password"
                value={passwords.confirm_password}
                error={passwordErrors.confirm_password}
                required
                onChange={(event) =>
                  setPasswords((current) => ({
                    ...current,
                    confirm_password: event.target.value,
                  }))
                }
              />
              <Button type="submit" icon={KeyRound} loading={changing}>
                Change password
              </Button>
            </form>
          </CardBody>
        </Card>

        {customer ? (
          <Card className="lg:col-span-2">
            <CardHeader
              title="Your customer record"
              description="The commercial party your quotations are addressed to"
              icon={Building2}
            />
            <CardBody>
              <div className="grid gap-6 sm:grid-cols-2">
                <div>
                  <p className="text-[15px] font-semibold text-navy-800">
                    {customer.company_name}
                  </p>
                  <p className="font-mono text-[12px] text-slate-500">{customer.code}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Badge tone={tierInfo(customer.tier).tone} size="sm">
                      {tierInfo(customer.tier).label} tier
                    </Badge>
                    <Badge tone={customerStatusInfo(customer.status).tone} size="sm">
                      {customerStatusInfo(customer.status).label}
                    </Badge>
                  </div>

                  {customer.billing_address ? (
                    <div className="mt-3 space-y-0.5">
                      <p className="text-[11.5px] font-semibold uppercase tracking-wide text-slate-500">
                        Billing address
                      </p>
                      {[
                        customer.billing_address.line1,
                        customer.billing_address.line2,
                        [
                          customer.billing_address.city,
                          customer.billing_address.postal_code,
                        ]
                          .filter(Boolean)
                          .join(' '),
                        [
                          customer.billing_address.state,
                          customer.billing_address.country,
                        ]
                          .filter(Boolean)
                          .join(', '),
                      ]
                        .filter(Boolean)
                        .map((line, index) => (
                          <p key={index} className="text-[12.5px] text-slate-600">
                            {line}
                          </p>
                        ))}
                    </div>
                  ) : null}
                </div>

                <div>
                  <DetailList>
                    <DetailRow label="Contact" value={customer.contact_name} />
                    <DetailRow label="Email" value={customer.email} />
                    <DetailRow label="Phone" value={customer.phone} />
                    {customer.tax_id ? (
                      <DetailRow label="Tax ID" value={customer.tax_id} mono />
                    ) : null}
                    <DetailRow
                      label="Credit limit"
                      value={
                        customer.credit_limit > 0
                          ? formatMoney(customer.credit_limit)
                          : 'Not set'
                      }
                    />
                    <DetailRow
                      label="Outstanding"
                      value={formatMoney(customer.outstanding_amount)}
                    />
                    <DetailRow
                      label="Available credit"
                      value={
                        customer.credit_limit > 0
                          ? formatMoney(customer.available_credit)
                          : 'No limit applied'
                      }
                    />
                  </DetailList>
                  <p className="mt-3 text-[11.5px] leading-snug text-slate-500">
                    To correct any of these details, contact your sales representative —
                    customer records are maintained by the sales team.
                  </p>
                </div>
              </div>
            </CardBody>
          </Card>
        ) : null}

        {isManager ? (
          <Card className="lg:col-span-2">
            <CardHeader
              title="Create a staff account"
              description="Provision a sales employee or another manager"
              icon={Shield}
            />
            <CardBody>
              <form onSubmit={createStaff} noValidate className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Input
                    label="Full name"
                    value={staff.full_name}
                    error={staffErrors.full_name}
                    required
                    onChange={(event) =>
                      setStaff((current) => ({
                        ...current,
                        full_name: event.target.value,
                      }))
                    }
                  />
                  <Input
                    label="Email address"
                    type="email"
                    value={staff.email}
                    error={staffErrors.email}
                    required
                    onChange={(event) =>
                      setStaff((current) => ({ ...current, email: event.target.value }))
                    }
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <Select
                    label="Role"
                    value={staff.role}
                    options={[
                      { value: 'SALES_EMPLOYEE', label: 'Sales Employee' },
                      { value: 'SALES_MANAGER', label: 'Sales Manager' },
                    ]}
                    onChange={(event) =>
                      setStaff((current) => ({ ...current, role: event.target.value }))
                    }
                  />
                  <Input
                    label="Initial password"
                    type="text"
                    value={staff.password}
                    error={staffErrors.password}
                    required
                    hint="They can change it after signing in"
                    onChange={(event) =>
                      setStaff((current) => ({
                        ...current,
                        password: event.target.value,
                      }))
                    }
                  />
                  <Input
                    label="Phone (optional)"
                    value={staff.phone}
                    onChange={(event) =>
                      setStaff((current) => ({ ...current, phone: event.target.value }))
                    }
                  />
                </div>
                <Button type="submit" icon={Shield} loading={creating}>
                  Create account
                </Button>
                <p className="text-[11.5px] leading-snug text-slate-500">
                  Customer accounts are created through self-registration, not here — a
                  customer login must be linked to a customer record, which registration
                  creates automatically.
                </p>
              </form>
            </CardBody>
          </Card>
        ) : null}
      </div>
    </>
  )
}
