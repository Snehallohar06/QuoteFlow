import { CheckCircle2 } from 'lucide-react'

const HIGHLIGHTS = [
  'Deterministic pricing with Decimal arithmetic — figures always reconcile',
  'Configurable discount tiers, enforced on every request',
  'Every decision recorded step by step and fully auditable',
  'Verified PDF quotations with an integrity digest',
]

/** The split-screen frame shared by the login and registration pages. */
export function AuthLayout({ title, description, children, footer }) {
  return (
    <div className="flex min-h-dvh bg-white">
      {/* Narrative panel: hidden on small screens, where the form is the point. */}
      <div className="relative hidden w-[46%] shrink-0 bg-navy-700 lg:flex lg:flex-col">
        <div className="flex items-center gap-2.5 px-10 pt-10">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500 text-white">
            <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" aria-hidden="true">
              <path
                d="M5 6h14M5 12h14M5 18h8"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                fill="none"
              />
            </svg>
          </span>
          <div>
            <p className="text-[17px] font-semibold leading-tight text-white">
              QuoteFlow
            </p>
            <p className="text-[11.5px] leading-tight text-navy-300">
              Quotation Management
            </p>
          </div>
        </div>

        <div className="flex flex-1 flex-col justify-center px-10 pb-16">
          <h2 className="max-w-md text-[26px] font-semibold leading-snug text-white">
            Automated quotation requests, from submission to verified document.
          </h2>
          <p className="mt-3 max-w-md text-[14px] leading-relaxed text-navy-200">
            Requests are validated, priced and routed by explicit business rules.
            Nothing is inferred, and every outcome can be explained.
          </p>

          <ul className="mt-8 space-y-3">
            {HIGHLIGHTS.map((item) => (
              <li key={item} className="flex items-start gap-2.5">
                <CheckCircle2
                  size={16}
                  className="mt-0.5 shrink-0 text-brand-400"
                  aria-hidden="true"
                />
                <span className="text-[13.5px] leading-snug text-navy-100">{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="px-10 pb-8 text-[11.5px] text-navy-400">
          Northwind Industrial Supplies · Sales Operations
        </p>
      </div>

      {/* Form panel */}
      <div className="flex min-w-0 flex-1 flex-col justify-center px-5 py-10 sm:px-10">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-7 flex items-center gap-2.5 lg:hidden">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500 text-white">
              <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" aria-hidden="true">
                <path
                  d="M5 6h14M5 12h14M5 18h8"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  fill="none"
                />
              </svg>
            </span>
            <p className="text-[17px] font-semibold text-navy-800">QuoteFlow</p>
          </div>

          <h1 className="text-[22px] font-semibold leading-tight text-navy-800">
            {title}
          </h1>
          {description ? (
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-slate-500">
              {description}
            </p>
          ) : null}

          <div className="mt-6">{children}</div>

          {footer ? <div className="mt-6">{footer}</div> : null}
        </div>
      </div>
    </div>
  )
}
