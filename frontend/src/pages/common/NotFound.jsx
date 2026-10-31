import { Link } from 'react-router-dom'
import { FileQuestion } from 'lucide-react'

export function NotFound() {
  return (
    <div className="flex flex-col items-center px-6 py-20 text-center">
      <span className="rounded-full bg-slate-100 p-3.5 text-slate-400">
        <FileQuestion size={24} aria-hidden="true" />
      </span>
      <h1 className="mt-4 text-[19px] font-semibold text-navy-800">Page not found</h1>
      <p className="mt-2 max-w-sm text-[13.5px] leading-relaxed text-slate-500">
        The page you were looking for does not exist, or has moved.
      </p>
      <Link
        to="/dashboard"
        className="mt-5 inline-flex h-9.5 items-center rounded-md bg-brand-600 px-4 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
      >
        Back to dashboard
      </Link>
    </div>
  )
}
