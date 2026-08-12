import { useEffect, useState } from 'react'

export default function useAnimatedCounter(target, duration = 1500) {
  const [count, setCount] = useState(0)

  useEffect(() => {
    let startTime = null
    let animationFrame

    const animate = (timestamp) => {
      if (!startTime) startTime = timestamp
      const progress = Math.min((timestamp - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setCount(Math.floor(eased * target))
      if (progress < 1) {
        animationFrame = requestAnimationFrame(animate)
      }
    }

    animationFrame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animationFrame)
  }, [target, duration])

  return count.toLocaleString()
}
