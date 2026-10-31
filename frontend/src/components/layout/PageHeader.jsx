import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

/**
 * The heading block at the top of every page.
 *
 * `breadcrumbs` is a list of `{ label, to }`; the last entry renders as plain
 * text because it is the current page.
 */
export function PageHeader({
  title,
  description,
  breadcrumbs,
  actions,
  meta,
  className = '',
}) {
  return (
    <div className={`mb-5 ${className}`}>
      {breadcrumbs?.length ? (
        <nav aria-label="Breadcrumb" className="mb-2">
          <ol className="flex flex-wrap items-center gap-1 text-[12.5px] text-slate-500">
            {breadcrumbs.map((crumb, index) => {
              const isLast = index === breadcrumbs.length - 1
              return (
                <li key={`${crumb.label}-${index}`} className="flex items-center gap-1">
                  {index > 0 ? (
                    <ChevronRight
                      size={13}
                      className="text-slate-300"
                      aria-hidden="true"
                    />
                  ) : null}
                  {isLast || !crumb.to ? (
                    <span
                      className={isLast ? 'font-medium text-slate-700' : undefined}
                      aria-current={isLast ? 'page' : undefined}
                    >
                      {crumb.label}
                    </span>
                  ) : (
                    <Link
                      to={crumb.to}
                      className="transition hover:text-brand-700 hover:underline"
                    >
                      {crumb.label}
                    </Link>
                  )}
                </li>
              )
            })}
          </ol>
        </nav>
      ) : null}

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[21px] font-semibold leading-tight text-navy-800 sm:text-[23px]">
              {title}
            </h1>
            {meta}
          </div>
          {description ? (
            <p className="mt-1.5 max-w-3xl text-[13.5px] leading-relaxed text-slate-500">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </div>
  )
}
