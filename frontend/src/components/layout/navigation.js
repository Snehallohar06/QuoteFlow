/**
 * Navigation, declared per role.
 *
 * This list drives the sidebar only. It is a convenience, not a security
 * boundary: every route is additionally wrapped in `ProtectedRoute`, and the
 * backend enforces the role on each endpoint regardless of what the client
 * renders.
 */

import {
  BarChart3,
  Bell,
  Boxes,
  Building2,
  ClipboardCheck,
  ClipboardList,
  FileSearch,
  FileText,
  LayoutDashboard,
  Package,
  PlusCircle,
  ScrollText,
  Settings,
  ShieldQuestion,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react'

import { ROLES } from '../../context/AuthContext'

export const NAVIGATION = {
  [ROLES.CUSTOMER]: [
    {
      heading: null,
      items: [
        { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { to: '/catalogue', label: 'Product Catalogue', icon: Boxes },
      ],
    },
    {
      heading: 'Quotations',
      items: [
        { to: '/requests/new', label: 'New Request', icon: PlusCircle },
        { to: '/requests', label: 'My Requests', icon: ClipboardList },
        { to: '/quotations', label: 'My Quotations', icon: FileText },
      ],
    },
    {
      heading: 'Account',
      items: [
        { to: '/notifications', label: 'Notifications', icon: Bell, badge: 'unread' },
      ],
    },
  ],

  [ROLES.SALES_EMPLOYEE]: [
    {
      heading: null,
      items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard }],
    },
    {
      heading: 'Processing',
      items: [
        { to: '/requests', label: 'Quotation Requests', icon: ClipboardList },
        {
          to: '/exceptions',
          label: 'Exception Management',
          icon: TriangleAlert,
          badge: 'exceptions',
        },
        { to: '/quotations', label: 'Quotations', icon: FileText },
        { to: '/approvals', label: 'Approval Queue', icon: ClipboardCheck, badge: 'pending' },
      ],
    },
    {
      heading: 'Master data',
      items: [
        { to: '/customers', label: 'Customers', icon: Building2 },
        { to: '/products', label: 'Products', icon: Package },
        {
          to: '/master-data-requests',
          label: 'My Add Requests',
          icon: ShieldQuestion,
        },
      ],
    },
    {
      heading: 'Insight',
      items: [
        { to: '/workflow-history', label: 'Workflow History', icon: FileSearch },
        { to: '/notifications', label: 'Notifications', icon: Bell, badge: 'unread' },
      ],
    },
  ],

  [ROLES.SALES_MANAGER]: [
    {
      heading: null,
      items: [
        { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { to: '/analytics', label: 'Analytics', icon: BarChart3 },
      ],
    },
    {
      heading: 'Decisions',
      items: [
        {
          to: '/approvals',
          label: 'Pending Approvals',
          icon: ClipboardCheck,
          badge: 'pending',
        },
        { to: '/requests', label: 'Quotation Requests', icon: ClipboardList },
        {
          to: '/exceptions',
          label: 'Exception Management',
          icon: TriangleAlert,
          badge: 'exceptions',
        },
        { to: '/quotations', label: 'Quotation History', icon: FileText },
      ],
    },
    {
      heading: 'Master data',
      items: [
        { to: '/customers', label: 'Customers', icon: Building2 },
        { to: '/products', label: 'Products', icon: Package },
        {
          to: '/master-data-requests',
          label: 'Add Requests',
          icon: ShieldQuestion,
          badge: 'masterData',
        },
      ],
    },
    {
      heading: 'Governance',
      items: [
        { to: '/workflow-history', label: 'Workflow History', icon: FileSearch },
        { to: '/audit-logs', label: 'Audit Logs', icon: ScrollText },
        { to: '/settings', label: 'Company Settings', icon: Settings },
        { to: '/notifications', label: 'Notifications', icon: Bell, badge: 'unread' },
        { to: '/verify', label: 'Verify a Quotation', icon: ShieldCheck },
      ],
    },
  ],
}

export function navigationFor(role) {
  return NAVIGATION[role] ?? []
}
