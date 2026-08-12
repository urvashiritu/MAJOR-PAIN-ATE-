import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ComposableMap, Geographies, Geography, Marker, useMapContext,
} from 'react-simple-maps'
import { getMapData } from '../../hooks/useApi'
import GlassCard from '../GlassCard'
import worldTopology from '../../data/countries-50m.json'

const geoUrl = worldTopology

function arcPath(x1, y1, x2, y2, curvature = 0.35) {
  const mx = (x1 + x2) / 2
  const my = (y1 + y2) / 2
  const dx = x2 - x1
  const dy = y2 - y1
  const cx = mx + dy * curvature
  const cy = my - dx * curvature * 0.5
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`
}

function ArcsLayer({ paths, onHover, hovered }) {
  const { projection } = useMapContext()

  return (
    <g>
      {paths.map(p => {
        const fromPx = projection(p.from.coords)
        const toPx = projection(p.to.coords)
        if (!fromPx || !toPx) return null
        const d = arcPath(fromPx[0], fromPx[1], toPx[0], toPx[1])

        return (
          <g key={p.id}>
            <motion.path
              d={d}
              fill="none"
              stroke="url(#travelGrad)"
              strokeWidth={2.5}
              strokeLinecap="round"
              
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 2, delay: 0.5, ease: 'easeInOut' }}
              onMouseEnter={() => onHover?.(p.id)}
              onMouseLeave={() => onHover?.(null)}
            />
            <motion.path
              d={d}
              fill="none"
              stroke="rgba(255,255,255,0.12)"
              strokeWidth={0.5}
              strokeDasharray="2 6"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 2, delay: 0.5, ease: 'easeInOut' }}
            />
            <circle r={3.5} fill="#e5484d" >
              <animateMotion dur="3.5s" repeatCount="indefinite" path={d} />
            </circle>
          </g>
        )
      })}
    </g>
  )
}

export default function WorldMap() {
  const [mapData, setMapData] = useState({ locations: [], travelPaths: [] })
  const [hoveredDot, setHoveredDot] = useState(null)
  const [hoveredPath, setHoveredPath] = useState(null)
  const [selectedDot, setSelectedDot] = useState(null)

  useEffect(() => {
    let mounted = true
    async function fetchData() {
      try {
        const data = await getMapData()
        if (mounted) setMapData(data)
      } catch {
        if (mounted) setMapData({ locations: [], travelPaths: [] })
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 15000)
    return () => { mounted = false; clearInterval(interval) }
  }, [])

  const { locations, travelPaths } = mapData

  const locMap = useMemo(() => {
    const m = {}
    locations.forEach(l => { m[l.name] = l })
    return m
  }, [locations])

  const paths = useMemo(() => {
    const filtered = selectedDot
      ? travelPaths.filter(p =>
          p.from.name === selectedDot || p.to.name === selectedDot
        )
      : travelPaths
    return filtered.map(p => ({
      ...p,
      from: p.from,
      to: p.to,
      id: `path-${p.from.name}-${p.to.name}`.replace(/\s/g, ''),
    }))
  }, [travelPaths, selectedDot])

  return (
    <GlassCard className="p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-white/80">Global Login Origins</h3>
          <span className="live-dot" />
        </div>
        <div className="flex items-center gap-3 text-[10px] text-white/35">
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-critical" /> Attack Path</span>
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-ochre" /> Flagged</span>
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-info" /> Normal</span>
        </div>
      </div>

      <div className="relative w-full" style={{ aspectRatio: '2.1/1' }}>
        <ComposableMap
          projection="geoMercator"
          projectionConfig={{ scale: 120, center: [15, 35] }}
          style={{ width: '100%', height: '100%' }}
        >
          <Geographies geography={geoUrl}>
            {({ geographies }) =>
              geographies.map(geo => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill="transparent"
                  stroke="rgba(255,255,255,0.3)"
                  strokeWidth={1}
                  onClick={() => setSelectedDot(null)}
                />
              ))
            }
          </Geographies>

          <ArcsLayer paths={paths} onHover={setHoveredPath} hovered={hoveredPath} />

          {locations.map(loc => {
            const isSelected = selectedDot === loc.name
            const isDimmed = selectedDot && !isSelected
            const dimOpacity = 0.08

            return (
              <Marker key={`${loc.name}-${loc.country}`} coordinates={loc.coords}>
                <g
                  onMouseEnter={() => setHoveredDot(loc.name)}
                  onMouseLeave={() => setHoveredDot(null)}
                  onClick={() => setSelectedDot(isSelected ? null : loc.name)}
                  style={{ cursor: 'pointer' }}
                >
                  <circle
                    r={loc.severity === 'critical' ? 6 : loc.severity === 'high' ? 4.5 : 3.5}
                    fill={loc.severity === 'critical' ? '#e5484d' : loc.severity === 'high' ? '#ff9b9e' : '#6ea8e8'}
                    opacity={isDimmed ? dimOpacity : 0.95}
                    style={{ transition: 'opacity 0.3s' }}
                  />
                  {!isDimmed && (
                    <circle
                      r={loc.severity === 'critical' ? 8 : loc.severity === 'high' ? 6 : 4}
                      fill="none"
                      stroke={loc.severity === 'critical' ? '#e5484d' : loc.severity === 'high' ? '#ff9b9e' : '#6ea8e8'}
                      strokeWidth={1.5}
                      opacity={0.3}
                      className="map-pulse"
                      style={{ animationDuration: '2.5s' }}
                    />
                  )}
                  {loc.severity === 'critical' && !isDimmed && (
<motion.circle
                      r={14}
                      fill="none"
                      stroke="#e5484d"
                      strokeWidth={1}
                      initial={{ opacity: 0.35, scale: 1 }}
                      animate={{ opacity: 0, scale: 1.8 }}
                      transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }}
                    />
                  )}
                </g>
              </Marker>
            )
          })}
        </ComposableMap>

        <svg style={{ position: 'absolute', width: 0, height: 0 }}>
          <defs>
            <linearGradient id="travelGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#6ea8e8" />
              <stop offset="50%" stopColor="#e8a33d" />
              <stop offset="100%" stopColor="#e5484d" />
            </linearGradient>
          </defs>
        </svg>

        <AnimatePresence>
          {hoveredPath && (() => {
            const p = paths.find(x => x.id === hoveredPath)
            if (!p) return null
            return (
              <motion.div
                key="path-tooltip"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                className="absolute top-2 right-2 chart-tooltip !p-2.5 !min-w-[180px]"
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="w-2 h-2 rounded-full bg-critical" />
                  <span className="text-xs font-semibold text-white/90">{p.type}</span>
                </div>
                <p className="text-xs text-white/70">
                  <span className="text-info">{p.from.name}</span>
                  <span className="px-1">→</span>
                  <span className="text-critical">{p.to.name}</span>
                </p>
                <p className="text-xs text-white/50 mt-0.5">{p.user} · {p.distance} · {p.timeGap}</p>
              </motion.div>
            )
          })()}

          {hoveredDot && (() => {
            const loc = locMap[hoveredDot]
            if (!loc) return null
            return (
              <motion.div
                key="dot-tooltip"
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                className="absolute bottom-2 left-2 chart-tooltip !p-2.5"
              >
                <p className="text-xs font-semibold text-white/90">{loc.user}</p>
                <p className="text-xs text-white/60">{loc.name}, {loc.country}</p>
                <span className="text-[10px] font-bold" style={{
                  color: loc.severity === 'critical' ? '#e5484d' : loc.severity === 'high' ? '#ff9b9e' : '#57b06c'
                }}>
                  Risk: {loc.risk}
                </span>
              </motion.div>
            )
          })()}
        </AnimatePresence>
      </div>
    </GlassCard>
  )
}
