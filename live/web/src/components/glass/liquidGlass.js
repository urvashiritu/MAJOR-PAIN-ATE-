export default function liquidGlass(el, opts = {}) {
  if (!el || typeof window === 'undefined') return { supported: false, refresh() {}, destroy() {} }

  const o = {
    scale: opts.scale ?? -112,
    chroma: opts.chroma ?? 6,
    border: opts.border ?? 0.07,
    mapBlur: opts.mapBlur ?? 12,
    blur: opts.blur ?? 3,
    saturate: opts.saturate ?? 1.5,
    radius: opts.radius ?? null,
    fallbackBlur: opts.fallbackBlur ?? 16,
  }

  const supportsFilter = CSS.supports('backdrop-filter', 'blur(1px)') ||
    CSS.supports('-webkit-backdrop-filter', 'blur(1px)')

  if (!supportsFilter) {
    el.style.backgroundColor = 'rgba(14,14,22,0.85)'
    return { supported: false, refresh() {}, destroy() {} }
  }

  const isChromium = !/Firefox|Safari|OPR\//.test(navigator.userAgent)

  if (!isChromium) {
    el.style.backdropFilter = `blur(${o.fallbackBlur}px) saturate(${o.saturate})`
    el.style.WebkitBackdropFilter = `blur(${o.fallbackBlur}px) saturate(${o.saturate})`
    return { supported: false, refresh() {}, destroy() {} }
  }

  const id = `lg_${Math.random().toString(36).slice(2, 9)}`
  let svg = null
  let mapDataUri = ''

  function generateMap() {
    const rect = el.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return

    const w = Math.min(rect.width, 800)
    const h = Math.min(rect.height, 800)
    const r = o.radius ?? parseFloat(getComputedStyle(el).borderRadius) || 28
    const insetPx = Math.min(w, h) * o.border

    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')

    ctx.fillStyle = 'rgb(128, 128, 0)'
    ctx.fillRect(0, 0, w, h)

    const rx = Math.min(r, w / 2)
    const ry = Math.min(r, h / 2)

    const gradient = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7)
    gradient.addColorStop(0, 'rgb(255, 0, 255)')
    gradient.addColorStop(0.5, 'rgb(128, 0, 128)')
    gradient.addColorStop(1, 'rgb(0, 128, 0)')

    ctx.save()
    ctx.beginPath()
    ctx.roundRect(insetPx, insetPx, w - insetPx * 2, h - insetPx * 2, Math.max(rx - insetPx, 0))
    ctx.fillStyle = gradient
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.beginPath()
    ctx.roundRect(0, 0, w, h, rx)
    ctx.fillStyle = 'transparent'
    ctx.globalCompositeOperation = 'difference'
    ctx.fillRect(0, 0, w, h)
    ctx.restore()

    ctx.save()
    ctx.filter = `blur(${o.mapBlur}px)`
    ctx.beginPath()
    ctx.roundRect(0, 0, w, h, rx)
    ctx.fillStyle = 'rgb(128, 128, 0)'
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.beginPath()
    ctx.roundRect(insetPx, insetPx, w - insetPx * 2, h - insetPx * 2, Math.max(rx - insetPx, 0))
    ctx.fillStyle = 'rgb(128, 128, 128)'
    ctx.fill()
    ctx.restore()

    mapDataUri = canvas.toDataURL()
  }

  function applyFilter() {
    generateMap()
    if (!mapDataUri) return

    if (svg) svg.remove()

    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    svg.setAttribute('width', '0')
    svg.setAttribute('height', '0')
    svg.style.position = 'absolute'
    svg.style.pointerEvents = 'none'
    svg.style.opacity = '0'

    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
    const filter = document.createElementNS('http://www.w3.org/2000/svg', 'filter')
    filter.setAttribute('id', id)
    filter.setAttribute('color-interpolation-filters', 'sRGB')
    filter.setAttribute('x', '-20%')
    filter.setAttribute('y', '-20%')
    filter.setAttribute('width', '140%')
    filter.setAttribute('height', '140%')

    const img = document.createElementNS('http://www.w3.org/2000/svg', 'feImage')
    img.setAttribute('href', mapDataUri)
    img.setAttribute('result', 'map')
    filter.appendChild(img)

    for (let i = 0; i < 3; i++) {
      const scale = o.scale + i * o.chroma
      const channel = i === 0 ? 'R' : i === 1 ? 'G' : 'B'

      const cm = document.createElementNS('http://www.w3.org/2000/svg', 'feColorMatrix')
      cm.setAttribute('type', 'matrix')
      const vals = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0]
      if (channel === 'R') vals[0] = 1
      if (channel === 'G') vals[6] = 1
      if (channel === 'B') vals[12] = 1
      cm.setAttribute('values', vals.join(' '))
      cm.setAttribute('result', `ch${i}`)
      filter.appendChild(cm)

      const dm = document.createElementNS('http://www.w3.org/2000/svg', 'feDisplacementMap')
      dm.setAttribute('in', 'SourceGraphic')
      dm.setAttribute('in2', `ch${i}`)
      dm.setAttribute('scale', scale.toString())
      dm.setAttribute('xChannelSelector', channel === 'R' ? 'R' : channel === 'G' ? 'G' : 'B')
      dm.setAttribute('yChannelSelector', channel === 'R' ? 'G' : channel === 'G' ? 'B' : 'R')
      dm.setAttribute('result', `disp${i}`)
      filter.appendChild(dm)
    }

    for (let i = 0; i < 2; i++) {
      const blend = document.createElementNS('http://www.w3.org/2000/svg', 'feBlend')
      blend.setAttribute('mode', 'screen')
      blend.setAttribute('in', i === 0 ? 'disp0' : `blend${i - 1}`)
      blend.setAttribute('in2', `disp${i + 1}`)
      blend.setAttribute('result', `blend${i}`)
      filter.appendChild(blend)
    }

    defs.appendChild(filter)
    svg.appendChild(defs)
    document.body.appendChild(svg)

    el.style.backdropFilter = `url(#${id}) blur(${o.blur}px) saturate(${o.saturate})`
    el.style.WebkitBackdropFilter = `url(#${id}) blur(${o.blur}px) saturate(${o.saturate})`
  }

  applyFilter()

  let resizeTimer
  function handleResize() {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(applyFilter, 100)
  }
  window.addEventListener('resize', handleResize)

  const ro = new ResizeObserver(() => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(applyFilter, 100)
  })
  ro.observe(el)

  return {
    supported: true,
    refresh: applyFilter,
    destroy() {
      if (svg) svg.remove()
      window.removeEventListener('resize', handleResize)
      ro.disconnect()
      el.style.backdropFilter = `blur(${o.fallbackBlur}px) saturate(${o.saturate})`
      el.style.WebkitBackdropFilter = `blur(${o.fallbackBlur}px) saturate(${o.saturate})`
    },
  }
}
