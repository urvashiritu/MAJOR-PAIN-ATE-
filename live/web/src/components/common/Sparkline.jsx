import { AreaChart, Area, ResponsiveContainer } from 'recharts'

export default function Sparkline({ data = [], color = '#3b82f6', height = 40 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id={`sparkline-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.25} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          fill={`url(#sparkline-${color.replace('#', '')})`}
          dot={false}
          animationDuration={600}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}