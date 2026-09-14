import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'

import type { Bounds } from '../api/types'
import { toLatLngTuple } from '../lib/geo'

/** Frames the map on mount. Give it a React `key` so it re-frames when the subject changes. */
export function FitBounds({ bounds }: { bounds: Bounds }) {
  const map = useMap()
  const initial = useRef(bounds)
  useEffect(() => {
    map.fitBounds(toLatLngTuple(initial.current), { padding: [32, 32] })
  }, [map])
  return null
}
