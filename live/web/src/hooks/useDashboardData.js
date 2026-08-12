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

    const interval = setInterval(fetchData, 30000)
    return () => { mounted = false; clearInterval(interval) }
  }, [])

  return { data, loading, error }
}
