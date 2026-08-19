import { useState, useEffect } from 'react'
import { getDashboard } from './useApi'

export default function useDashboardData() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let mounted = true

    async function fetchData() {
      try {
        setLoading(true)
        const result = await getDashboard()
        if (mounted) {
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (mounted) setError(err.message)
      } finally {
        if (mounted) setLoading(false)
      }
    }

    fetchData()

    let sse = null
    try {
      sse = new EventSource('/events/stream')
      // Flask emits NAMED events ("event: score"), so plain onmessage never
      // fires; subscribe to the 'score' event for instant updates. The 2s
      // polling below is the fallback when SSE is down.
      sse.addEventListener('score', () => fetchData())
      // Do not close on error: EventSource auto-reconnects, and the 2s
      // polling fallback below keeps the dashboard alive meanwhile.
    } catch {
      sse = null
    }

    const interval = setInterval(fetchData, 2000)
    return () => { mounted = false; clearInterval(interval); sse?.close() }
  }, [])

  return { data, loading, error }
}