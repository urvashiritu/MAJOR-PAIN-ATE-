import { Fingerprint, Keyboard } from 'lucide-react'

function Row({ Icon, label, ok, value, tone }) {
  const color = ok ? '#57b06c' : '#e5484d'
  return (
    <div className="flex items-center justify-between py-2 border-b border-white/[0.04] last:border-0">
      <div className="flex items-center gap-2">
        <Icon size={13} style={{ color: tone === 'muted' ? '#ffffff40' : color }} />
        <span className="text-xs text-white/50">{label}</span>
      </div>
      <span className="text-sm font-medium" style={{ color: tone === 'muted' ? '#ffffff60' : color }}>
        {value}
      </span>
    </div>
  )
}

export default function BehavioralIndicators({ baseline }) {
  const fp = baseline?.fingerprint || 'unknown'
  const typing = baseline?.typingMatch || 'unknown'
  const pct = baseline?.typingPct

  const fpText = fp === 'match' ? 'MATCH ✓' : fp === 'new' ? 'NEW DEVICE' : fp === 'mismatch' ? 'MISMATCH ⚠' : '—'
  const fpOk = fp === 'match'
  const fpTone = fp === 'unknown' ? 'muted' : null

  const typingText = typing === 'unknown' ? '—' : typing === 'match' ? `MATCH ${pct ?? ''}%` : `MISMATCH ${pct ?? ''}%`
  const typingOk = typing === 'match'
  const typingTone = typing === 'unknown' ? 'muted' : null

  return (
    <div>
      <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3">Behavioral Overlay</h4>
      <div className="panel-inset p-4">
        <Row Icon={Fingerprint} label="Device Fingerprint" ok={fpOk} value={fpText} tone={fpTone} />
        <Row Icon={Keyboard} label="Typing Rhythm" ok={typingOk} value={typingText} tone={typingTone} />
      </div>
      <p className="mt-2 text-[11px] text-white/30 leading-relaxed">
        Demo overlay — compares this login against the user's accepted-login baseline. Support signal, not a security boundary.
      </p>
    </div>
  )
}