import { useEffect, useRef } from 'react'
import liquidGlass from './liquidGlass'

export default function useLiquidGlass(opts = {}) {
  const ref = useRef(null)

  useEffect(() => {
    if (!ref.current) return
    const glass = liquidGlass(ref.current, opts)
    return () => glass.destroy()
  }, [])

  return ref
}
