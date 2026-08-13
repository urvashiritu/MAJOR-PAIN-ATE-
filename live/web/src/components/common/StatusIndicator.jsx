import { cn } from '../../lib/utils'

const stateColors = {
  active: { dot: 'bg-low', ping: 'bg-low' },
  down: { dot: 'bg-critical', ping: 'bg-critical' },
  fixing: { dot: 'bg-ochre', ping: 'bg-ochre' },
  idle: { dot: 'bg-white/30', ping: 'bg-white/20' },
}

const sizeClasses = {
  sm: { dot: 'h-2 w-2', ping: 'h-2 w-2' },
  lg: { dot: 'h-4 w-4', ping: 'h-4 w-4' },
  md: { dot: 'h-3 w-3', ping: 'h-3 w-3' },
}

export default function StatusIndicator({
  state = 'idle',
  label,
  className,
  size = 'md',
  labelClassName,
}) {
  const shouldAnimate = state === 'active' || state === 'fixing' || state === 'down'
  const colors = stateColors[state] || stateColors.idle
  const dims = sizeClasses[size] || sizeClasses.md

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="relative flex items-center">
        {shouldAnimate && (
          <span className={cn('absolute inline-flex rounded-full opacity-75 animate-ping', dims.ping, colors.ping)} />
        )}
        <span className={cn('relative inline-flex rounded-full', dims.dot, colors.dot)} />
      </div>
      {label && (
        <p className={cn('text-sm text-ink/dim', labelClassName)}>{label}</p>
      )}
    </div>
  )
}