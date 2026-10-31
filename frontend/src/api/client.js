/**
 * The single Axios instance every API module shares.
 *
 * Responsibilities:
 *  - attach the bearer token to each request
 *  - refresh the access token once on a 401, then replay the original request
 *  - normalise the backend's `{error: {code, message, details}}` envelope into
 *    an Error the UI can render without knowing about Axios
 */

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const ACCESS_TOKEN_KEY = 'quoteflow.access_token'
export const REFRESH_TOKEN_KEY = 'quoteflow.refresh_token'

/** Paths that must never trigger a refresh-and-retry cycle. */
const AUTH_PATHS = ['/api/v1/auth/login', '/api/v1/auth/refresh', '/api/v1/auth/register']

export const tokenStore = {
  get access() {
    try {
      return localStorage.getItem(ACCESS_TOKEN_KEY)
    } catch {
      return null
    }
  },
  get refresh() {
    try {
      return localStorage.getItem(REFRESH_TOKEN_KEY)
    } catch {
      return null
    }
  },
  set({ access_token, refresh_token }) {
    try {
      if (access_token) localStorage.setItem(ACCESS_TOKEN_KEY, access_token)
      if (refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token)
    } catch {
      /* Private browsing with storage blocked: the session stays in memory. */
    }
  },
  clear() {
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY)
      localStorage.removeItem(REFRESH_TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
}

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = tokenStore.access
  if (token && !config.skipAuth) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/**
 * An `ApiError` carries the backend's structured error so a form can show
 * field-level detail and a toast can show the message.
 */
export class ApiError extends Error {
  constructor({ message, code, details, status }) {
    super(message)
    this.name = 'ApiError'
    this.code = code ?? 'unknown_error'
    this.details = details ?? null
    this.status = status ?? 0
  }

  /** True when the caller is not signed in, or the token expired. */
  get isAuth() {
    return this.status === 401
  }

  /** True when the caller is signed in but lacks the role. */
  get isForbidden() {
    return this.status === 403
  }

  get isNotFound() {
    return this.status === 404
  }

  /**
   * Field errors from FastAPI's request-validation handler, keyed by field
   * name, so a form can render them inline.
   */
  get fieldErrors() {
    if (!Array.isArray(this.details)) return {}
    const fields = {}
    for (const item of this.details) {
      // FastAPI: {loc: ['body', 'email'], msg: '...'}
      if (Array.isArray(item?.loc)) {
        const name = item.loc.filter((part) => part !== 'body').join('.')
        if (name) fields[name] = item.msg
      }
      // Our settings handler: {field: 'tax_policy.rate_percent', message: '...'}
      else if (item?.field) {
        fields[item.field] = item.message
      }
    }
    return fields
  }
}

function toApiError(error) {
  // The request never reached the server, or it timed out.
  if (!error.response) {
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false
    return new ApiError({
      message: offline
        ? 'You appear to be offline. Check your connection and try again.'
        : 'Could not reach the QuoteFlow API. Is the backend running on port 8000?',
      code: error.code === 'ECONNABORTED' ? 'timeout' : 'network_error',
      status: 0,
    })
  }

  const { status, data } = error.response
  const envelope = data?.error

  if (envelope) {
    return new ApiError({
      message: envelope.message || 'The request failed.',
      code: envelope.code,
      details: envelope.details,
      status,
    })
  }

  // A response that did not come from our handlers (e.g. a proxy error page).
  return new ApiError({
    message:
      typeof data === 'string' && data.length < 200
        ? data
        : `The request failed with status ${status}.`,
    code: `http_${status}`,
    status,
  })
}

/** Serialises concurrent 401s so only one refresh call is made. */
let refreshInFlight = null

/** Set by AuthContext so a failed refresh can clear the session and redirect. */
let onSessionExpired = () => {}
export function setSessionExpiredHandler(handler) {
  onSessionExpired = handler
}

async function refreshAccessToken() {
  const refresh_token = tokenStore.refresh
  if (!refresh_token) throw new Error('no refresh token')

  const response = await axios.post(
    `${BASE_URL}/api/v1/auth/refresh`,
    { refresh_token },
    { headers: { 'Content-Type': 'application/json' }, timeout: 15000 }
  )
  tokenStore.set(response.data)
  return response.data.access_token
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config ?? {}
    const status = error.response?.status
    const url = `${config.baseURL ?? ''}${config.url ?? ''}`
    const isAuthCall = AUTH_PATHS.some((path) => url.includes(path))

    if (status === 401 && !config._retried && !isAuthCall && tokenStore.refresh) {
      config._retried = true
      try {
        refreshInFlight = refreshInFlight ?? refreshAccessToken()
        const token = await refreshInFlight
        refreshInFlight = null
        config.headers = { ...config.headers, Authorization: `Bearer ${token}` }
        return api.request(config)
      } catch {
        refreshInFlight = null
        tokenStore.clear()
        onSessionExpired()
      }
    }

    return Promise.reject(toApiError(error))
  }
)

/** Strips empty filter values so they are not sent as `?search=`. */
export function cleanParams(params = {}) {
  const output = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    output[key] = value
  }
  return output
}

export const API_ORIGIN = BASE_URL
