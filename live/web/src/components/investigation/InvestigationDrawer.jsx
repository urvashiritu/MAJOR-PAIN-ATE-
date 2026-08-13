import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, AlertTriangle, CheckCircle, Shield, FileText,
  Ban, Flag, ArrowUpRight, Download, MessageSquare,
} from 'lucide-react'
import SeverityBadge from '../common/SeverityBadge'
import BehavioralIndicators from './BehavioralIndicators'
import { getInvestigation, acknowledgeAlert } from '../../hooks/useApi'

function EventTimeline({ timeline }) {
  const iconMap = {
    x: { icon: X, color: '#e5484d', bg: 'bg-critical/10' },
    check: { icon: CheckCircle, color: '#57b06c', bg: 'bg-low/10' },
    shield: { icon: Shield, color: '#e8a33d', bg: 'bg-ochre/10' },
    file: { icon: FileText, color: '#e5484d', bg: 'bg-critical/10' },
  }

  return (
    <div>
      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-4">Event Timeline</h4>
      <div className="relative">
        <div className="absolute left-[13px] top-3 bottom-3 w-px bg-white/[0.05]" />
        <div className="space-y-4">
          {timeline.map((event, i) => {
            const m = iconMap[event.icon] || iconMap.x
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.07 }}
                className="flex gap-3"
              >
                <div className={`w-7 h-7 rounded-full ${m.bg} flex items-center justify-center flex-shrink-0 z-10`}>
                  <m.icon size={12} style={{ color: m.color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white/80">{event.event}</span>
                    {event.severity === 'critical' && <SeverityBadge severity="critical" label="Critical" />}
                    {event.severity === 'high' && !event.event.includes('Failed') && <SeverityBadge severity="high" label="High" />}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs font-mono text-white/40">{event.time}</span>
                    <span className="text-xs text-white/40">·</span>
                    <span className="text-xs text-white/40">{event.country}</span>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function FeatureContributions({ contributions }) {
  return (
    <div>
      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">Feature Contribution</h4>
      <div className="space-y-2.5">
        {contributions.map((item, i) => (
          <div key={item.feature}>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-sm text-white/70">{item.feature}</span>
              <motion.span className="text-sm font-bold" style={{ color: item.color }} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                +{item.value}
              </motion.span>
            </div>
            <div className="h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
              <motion.div
                className="h-full rounded-full"
                style={{ backgroundColor: item.color }}
                initial={{ width: 0 }}
                animate={{ width: `${(item.value / 50) * 100}%` }}
                transition={{ duration: 0.6, delay: i * 0.08, ease: [0.4, 0, 0.2, 1] }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function AIExplanation({ explanation, confidence }) {
  const value = typeof confidence === 'number' && confidence <= 1 ? Math.round(confidence * 100) : (confidence || 0)
  return (
    <div>
      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">AI Analysis</h4>
      <div className="panel-inset p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium text-white/50">Ensemble Confidence</span>
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-20 rounded-full bg-white/[0.04] overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-purple-500"
                initial={{ width: 0 }}
                animate={{ width: `${value}%` }}
                transition={{ duration: 1, ease: [0.4, 0, 0.2, 1] }}
              />
            </div>
            <span className="text-sm font-bold text-purple-400">{value}%</span>
          </div>
        </div>
        <div className="text-sm text-white/60 leading-relaxed whitespace-pre-line">
          {explanation}
        </div>
      </div>
    </div>
  )
}

function UserBaseline({ baseline }) {
  return (
    <div>
      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">User Baseline Profile</h4>
      <div className="panel-inset p-4">
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Avg Login', value: baseline.avgLoginHour },
            { label: 'Avg Logout', value: baseline.avgLogoutHour },
            { label: 'Logins/Day', value: baseline.avgLoginsPerDay },
            { label: 'MFA', value: baseline.mfaEnabled ? 'Enabled' : 'Disabled' },
          ].map(d => (
            <div key={d.label}>
              <p className="text-xs text-white/40">{d.label}</p>
              <p className="text-sm font-medium text-white/80">{d.value}</p>
            </div>
          ))}
          <div className="col-span-2">
            <p className="text-xs text-white/40 mb-1">Known Countries</p>
            <div className="flex flex-wrap gap-1">
              {(baseline.countries || []).map(c => (
                <span key={c} className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-white/60">{c}</span>
              ))}
            </div>
          </div>
          <div className="col-span-2">
            <p className="text-xs text-white/40 mb-1">Known Devices</p>
            {(baseline.devices || []).map(d => (
              <p key={d} className="text-xs text-white/60">{d}</p>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function MitreCard({ mitreId, mitreName, mitreDescription }) {
  return (
    <div>
      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">MITRE ATT&CK</h4>
      <div className="panel-inset p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-critical/10 text-critical">{mitreId}</span>
          <span className="text-sm font-medium text-white/80">{mitreName}</span>
        </div>
        <p className="text-xs text-white/50 leading-relaxed">{mitreDescription}</p>
        <button className="mt-2 text-xs text-info hover:text-info transition-colors flex items-center gap-1">
          View in MITRE ATT&CK <ArrowUpRight size={10} />
        </button>
      </div>
    </div>
  )
}

export default function InvestigationDrawer({ isOpen, onClose, alert }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(null)
  const overlay = alert || null
  const [noteText, setNoteText] = useState('')
  const [showNoteInput, setShowNoteInput] = useState(false)
  const [alertAcked, setAlertAcked] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    let mounted = true
    setData(null)
    setLoadError(null)
    setLoading(true)
    getInvestigation(alert?.eventId ?? alert?.id)
      .then(d => { if (mounted) { setData(d); setLoading(false); setAlertAcked(alert?.status === 'acknowledged') } })
      .catch(e => { if (mounted) { setLoadError(e.message); setLoading(false) } })
    return () => { mounted = false }
  }, [isOpen, alert])

  const handleAck = async () => {
    if (!alert) return
    try {
      await acknowledgeAlert(alert.id)
      setAlertAcked(true)
    } catch { /* keep local state unchanged */ }
  }

  if (isOpen && !data && !loading) {
    return (
      <AnimatePresence>
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={onClose}
          />
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 280 }}
            className="fixed right-0 top-0 h-full w-full max-w-lg z-50 overflow-y-auto"
            style={{ borderLeft: '1px solid rgba(255,255,255,0.06)' }}
          >
            <div className="min-h-full panel p-5">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-base font-semibold text-white">Investigation</h2>
                <button onClick={onClose} className="p-1.5 rounded-sm hover:bg-white/5 text-white/40 hover:text-white/70 transition-all">
                  <X size={16} />
                </button>
              </div>
              <div className="panel-inset p-4 mb-4">
                <div className="flex items-center gap-2">
                  {overlay && <SeverityBadge severity={overlay.severity} pulse />}
                  <span className="text-sm text-white/70">{overlay?.displayName || overlay?.user}</span>
                  <span className="text-xs text-white/40">{overlay?.type}</span>
                </div>
                <p className="text-xs text-critical/80 mt-2">Investigation data unavailable: {loadError || 'unknown error'}</p>
              </div>
              <button onClick={onClose} className="w-full px-3 py-2.5 rounded-sm bg-white/5 text-white/60 text-sm font-medium hover:bg-white/10 transition-all">
                Close
              </button>
            </div>
          </motion.div>
        </>
      </AnimatePresence>
    )
  }

  if (loading) {
    return (
      <AnimatePresence>
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={onClose}
          />
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 280 }}
            className="fixed right-0 top-0 h-full w-full max-w-lg z-50 overflow-y-auto"
            style={{ borderLeft: '1px solid rgba(255,255,255,0.06)' }}
          >
            <div className="min-h-full panel p-5">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-base font-semibold text-white">Investigation</h2>
                <button onClick={onClose} className="p-1.5 rounded-sm hover:bg-white/5 text-white/40 hover:text-white/70 transition-all">
                  <X size={16} />
                </button>
              </div>
              <div className="space-y-3">
                <div className="h-20 rounded-sm bg-white/[0.03] animate-pulse" />
                <div className="h-40 rounded-sm bg-white/[0.03] animate-pulse" />
                <div className="h-40 rounded-sm bg-white/[0.03] animate-pulse" />
              </div>
            </div>
          </motion.div>
        </>
      </AnimatePresence>
    )
  }

  const d = data
  const riskScore = overlay?.riskScore ?? d?.riskScore ?? 0

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={onClose}
          />
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 280 }}
            className="fixed right-0 top-0 h-full w-full max-w-lg z-50 overflow-y-auto"
            style={{ borderLeft: '1px solid rgba(255,255,255,0.06)' }}
          >
            <div className="min-h-full panel p-5">
              {/* Header */}
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-base font-semibold text-white">Investigation</h2>
                <button onClick={onClose} className="p-1.5 rounded-sm hover:bg-white/5 text-white/40 hover:text-white/70 transition-all">
                  <X size={16} />
                </button>
              </div>

              {/* Summary Card */}
              <div className="panel-inset p-4 mb-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={overlay?.severity || d.severity} pulse />
                    <span className="text-xs text-white/40">{overlay?.mitreId || d.mitreId}</span>
                    {alertAcked && <span className="badge badge-info">Acknowledged</span>}
                  </div>
                  <div className="text-right">
                    <motion.span
                      className={`text-3xl font-bold ${riskScore >= 70 ? 'text-critical' : riskScore >= 40 ? 'text-ochre' : 'text-low'}`}
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ type: 'spring', damping: 10 }}
                    >
                      {riskScore}
                    </motion.span>
                    <div className="text-[10px] text-white/25 font-medium">RISK</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                  <div>
                    <p className="text-xs text-white/40">User</p>
                    <p className="font-medium text-white/90">{d.displayName || d.user}</p>
                    <p className="text-xs text-white/40">@{d.user}</p>
                  </div>
                  <div>
                    <p className="text-xs text-white/40">Alert Type</p>
                    <p className="font-medium text-white/90">{d.type || overlay?.type || '—'}</p>
                    <p className="text-xs text-white/40">{overlay?.description ? overlay.description.slice(0, 40) + '…' : ''}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-x-5 gap-y-2 text-xs">
                  <div><p className="text-white/40">IP</p><p className="font-mono text-white/80">{d.ip}</p></div>
                  <div><p className="text-white/40">ASN</p><p className="text-white/80">{d.asn}</p></div>
                  <div><p className="text-white/40">Country</p><p className="text-critical font-medium">{d.country}</p></div>
                  <div><p className="text-white/40">Previous</p><p className="text-white/80">{d.previousCountry}</p></div>
                  <div><p className="text-white/40">Device</p><p className="text-white/80">{d.device}</p></div>
                  <div><p className="text-white/40">Browser</p><p className="text-white/80">{d.browser}</p></div>
                  <div><p className="text-white/40">OS</p><p className="text-white/80">{d.os}</p></div>
                  <div><p className="text-white/40">Distance</p><p className="text-critical font-medium">{d.distanceKm.toLocaleString()} km</p></div>
                </div>

                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-white/[0.04] text-sm">
                  <AlertTriangle size={13} className="text-critical flex-shrink-0" />
                  <span className="text-critical font-medium">{d.type}</span>
                  <span className="text-white/50">— {d.previousCity} → {d.city} in {d.timeSincePreviousLogin}</span>
                </div>
              </div>

              {/* Content Sections */}
              <div className="space-y-5">
                <EventTimeline timeline={d.timeline} />
                <FeatureContributions contributions={d.featureContributions} />
                <BehavioralIndicators baseline={d.baseline} />
                <MitreCard mitreId={d.mitreId} mitreName={d.mitreName} mitreDescription={d.mitreDescription} />
                <AIExplanation explanation={d.aiExplanation} confidence={d.confidence} />
                <UserBaseline baseline={d.baseline} />
              </div>

              {/* Analyst Notes */}
              <div className="mt-5 pt-4 border-t border-white/[0.04]">
                <button
                  onClick={() => setShowNoteInput(!showNoteInput)}
                  className="flex items-center gap-1.5 text-sm text-white/50 hover:text-white/70 transition-colors"
                >
                  <MessageSquare size={14} />
                  {showNoteInput ? 'Cancel' : 'Add Analyst Note'}
                </button>
                <AnimatePresence>
                  {showNoteInput && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <textarea
                        value={noteText}
                        onChange={e => setNoteText(e.target.value)}
                        placeholder="Type your analysis notes..."
                        rows={3}
                        className="glass-input w-full mt-2 p-2.5 text-xs resize-none"
                      />
                      <div className="flex gap-2 mt-2">
                        <button className="px-3 py-1.5 text-xs rounded-sm bg-info/10 text-info hover:bg-info/20 transition-all">
                          Save Note
                        </button>
                        <button onClick={() => { setShowNoteInput(false); setNoteText('') }} className="px-3 py-1.5 text-xs rounded-sm bg-white/5 text-white/50 hover:bg-white/10 transition-all">
                          Cancel
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Action Buttons */}
              <div className="flex gap-2 mt-5 pt-4 border-t border-white/[0.04]">
                <button
                  onClick={handleAck}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-sm text-sm font-medium transition-all ${
                    alertAcked
                      ? 'bg-low/10 text-low'
                      : 'bg-info/10 text-info hover:bg-info/20'
                  }`}
                >
                  <CheckCircle size={14} />
                  {alertAcked ? 'Acknowledged' : 'Acknowledge'}
                </button>
                <button className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-sm bg-critical/10 text-critical text-sm font-medium hover:bg-critical/20 transition-all">
                  <Ban size={14} />
                  Contain
                </button>
                <button className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-sm bg-ochre/10 text-ochre text-sm font-medium hover:bg-ochre/20 transition-all">
                  <Flag size={14} />
                  Escalate
                </button>
                <button className="px-3 py-2.5 rounded-sm bg-white/5 text-white/50 hover:bg-white/10 transition-all" title="Export Report">
                  <Download size={14} />
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
