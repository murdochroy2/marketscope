import type { ReactNode } from 'react'
import { MapContainer, TileLayer } from 'react-leaflet'

import type { Bounds } from '../api/types'
import { toLatLngTuple } from '../lib/geo'

interface Props {
  bounds: Bounds
  children?: ReactNode
}

/** OpenStreetMap tiles on a canvas renderer, which keeps thousands of store markers smooth. */
export function BaseMap({ bounds, children }: Props) {
  return (
    <MapContainer
      className="map"
      bounds={toLatLngTuple(bounds)}
      boundsOptions={{ padding: [24, 24] }}
      preferCanvas
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={19}
      />
      {children}
    </MapContainer>
  )
}
