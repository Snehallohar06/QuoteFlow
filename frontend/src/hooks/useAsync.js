import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Run an async loader and track its state.
 *
 * Returns `{ data, error, loading, reload, setData }`. The loader is re-run
 * whenever `deps` change. In-flight results from a superseded run are
 * discarded, so fast filter typing cannot leave stale data on screen.
 */
export function useAsync(loader, deps = [], { immediate = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(immediate)

  // Each run gets a token; only the newest run is allowed to set state.
  const runToken = useRef(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const execute = useCallback(async () => {
    const token = ++runToken.current
    setLoading(true)
    setError(null)
    try {
      const result = await loader()
      if (mounted.current && token === runToken.current) {
        setData(result)
      }
      return result
    } catch (caught) {
      if (mounted.current && token === runToken.current) {
        setError(caught)
      }
      return undefined
    } finally {
      if (mounted.current && token === runToken.current) {
        setLoading(false)
      }
    }
    // `deps` is forwarded from the caller rather than written inline, which is
    // the whole point of a generic data hook: each page declares what its own
    // loader depends on. Both lint rules below can only verify a literal array,
    // so they are switched off here by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/use-memo
  }, deps)

  useEffect(() => {
    if (immediate) execute()
  }, [execute, immediate])

  return { data, error, loading, reload: execute, setData }
}

/**
 * Track a one-off mutation (submit, approve, delete).
 *
 * `run` resolves with the result and re-throws nothing — inspect `error`, or
 * use the returned value, so a component never needs its own try/catch for
 * loading state alone.
 */
export function useMutation(mutator) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  const run = useCallback(
    async (...args) => {
      setPending(true)
      setError(null)
      try {
        return { ok: true, data: await mutator(...args) }
      } catch (caught) {
        setError(caught)
        return { ok: false, error: caught }
      } finally {
        setPending(false)
      }
    },
    [mutator]
  )

  return { run, pending, error, reset: () => setError(null) }
}
