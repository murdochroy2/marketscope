import L from 'leaflet'
import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'

import type { Bounds } from '../api/types'
import { center, normalize, toLatLngTuple, translate } from '../lib/geo'

type LatEdge = 'south' | 'north' | null
type LngEdge = 'west' | 'east' | null

interface HandleSpec {
  lat: LatEdge
  lng: LngEdge
  cursor: string
}

// Four corners resize both axes; four edge midpoints resize one.
const HANDLES: HandleSpec[] = [
  { lat: 'north', lng: 'west', cursor: 'nwse-resize' },
  { lat: 'north', lng: 'east', cursor: 'nesw-resize' },
  { lat: 'south', lng: 'east', cursor: 'nwse-resize' },
  { lat: 'south', lng: 'west', cursor: 'nesw-resize' },
  { lat: 'north', lng: null, cursor: 'ns-resize' },
  { lat: 'south', lng: null, cursor: 'ns-resize' },
  { lat: null, lng: 'west', cursor: 'ew-resize' },
  { lat: null, lng: 'east', cursor: 'ew-resize' },
]

function handlePosition(b: Bounds, spec: HandleSpec): L.LatLngExpression {
  const [midLat, midLng] = center(b)
  return [spec.lat ? b[spec.lat] : midLat, spec.lng ? b[spec.lng] : midLng]
}

const handleIcon = (cursor: string) =>
  L.divIcon({ className: 'rect-handle', html: `<span style="cursor:${cursor}"></span>`, iconSize: [14, 14] })

// The map uses the canvas renderer, so colours must go through Leaflet styles, not CSS.
const WITHIN_LIMIT_STYLE: L.PathOptions = { color: '#0f6b5c', fillColor: '#0f6b5c' }
const OVER_LIMIT_STYLE: L.PathOptions = { color: '#b1306f', fillColor: '#b1306f' }

const moveIcon = L.divIcon({
  className: 'rect-move',
  html: '<span title="Drag to move the boundary" aria-label="Move boundary">✥</span>',
  iconSize: [30, 30],
})

interface Props {
  bounds: Bounds
  overLimit: boolean
  onChange: (bounds: Bounds) => void
}

/**
 * A rectangle the user can resize from corners and edges and move from its centre.
 *
 * Leaflet is driven imperatively so dragging stays at 60 fps. React state is updated on
 * every drag event, which keeps the area readout live, but the Leaflet layers are never
 * rebuilt while a drag is in progress.
 */
export function RectangleEditor({ bounds, overLimit, onChange }: Props) {
  const map = useMap()
  const boundsRef = useRef(bounds)
  const dragging = useRef(false)
  const onChangeRef = useRef(onChange)
  const layers = useRef<{ rect: L.Rectangle; handles: L.Marker[]; move: L.Marker } | null>(null)

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    const rect = L.rectangle(toLatLngTuple(boundsRef.current), {
      ...WITHIN_LIMIT_STYLE,
      weight: 2.5,
      fillOpacity: 0.08,
      interactive: false,
    }).addTo(map)

    const sync = (next: Bounds, except?: L.Marker) => {
      boundsRef.current = next
      rect.setBounds(toLatLngTuple(next))
      handles.forEach((h, i) => h !== except && h.setLatLng(handlePosition(next, HANDLES[i])))
      if (move !== except) move.setLatLng(center(next))
      onChangeRef.current(next)
    }

    const handles = HANDLES.map((spec) => {
      const marker = L.marker(handlePosition(boundsRef.current, spec), {
        icon: handleIcon(spec.cursor),
        draggable: true,
        keyboard: false,
      }).addTo(map)
      marker.on('dragstart', () => (dragging.current = true))
      marker.on('drag', () => {
        const { lat, lng } = marker.getLatLng()
        const next = { ...boundsRef.current }
        if (spec.lat) next[spec.lat] = lat
        if (spec.lng) next[spec.lng] = lng
        sync(normalize(next), marker)
      })
      marker.on('dragend', () => {
        dragging.current = false
        sync(boundsRef.current) // snap every handle back onto the final rectangle
      })
      return marker
    })

    let moveOrigin: { lat: number; lng: number; bounds: Bounds } | null = null
    const move = L.marker(center(boundsRef.current), { icon: moveIcon, draggable: true, keyboard: false }).addTo(map)
    move.on('dragstart', () => {
      dragging.current = true
      const { lat, lng } = move.getLatLng()
      moveOrigin = { lat, lng, bounds: boundsRef.current }
    })
    move.on('drag', () => {
      if (!moveOrigin) return
      const { lat, lng } = move.getLatLng()
      sync(translate(moveOrigin.bounds, lat - moveOrigin.lat, lng - moveOrigin.lng), move)
    })
    move.on('dragend', () => {
      dragging.current = false
      moveOrigin = null
    })

    layers.current = { rect, handles, move }
    return () => {
      rect.remove()
      handles.forEach((h) => h.remove())
      move.remove()
      layers.current = null
    }
  }, [map])

  // Accept bounds pushed from outside (reset, new city) without fighting an active drag.
  useEffect(() => {
    const current = layers.current
    if (!current || dragging.current) return
    const b = boundsRef.current
    if (b.south === bounds.south && b.west === bounds.west && b.north === bounds.north && b.east === bounds.east) {
      return
    }
    boundsRef.current = bounds
    current.rect.setBounds(toLatLngTuple(bounds))
    current.handles.forEach((h, i) => h.setLatLng(handlePosition(bounds, HANDLES[i])))
    current.move.setLatLng(center(bounds))
  }, [bounds])

  useEffect(() => {
    layers.current?.rect.setStyle(overLimit ? OVER_LIMIT_STYLE : WITHIN_LIMIT_STYLE)
  }, [overLimit])

  return null
}
