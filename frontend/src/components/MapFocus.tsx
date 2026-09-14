import L from 'leaflet'
import { useEffect } from 'react'
import { useMap } from 'react-leaflet'

export interface FocusTarget {
  key: string
  lat: number
  lng: number
  title: string
  subtitle: string
}

/** Flies to a store picked in the list and opens a popup there. */
export function MapFocus({ target }: { target: FocusTarget | null }) {
  const map = useMap()
  useEffect(() => {
    if (!target) return
    map.flyTo([target.lat, target.lng], Math.max(map.getZoom(), 16), { duration: 0.6 })
    const content = document.createElement('div')
    const title = document.createElement('strong')
    title.textContent = target.title
    const subtitle = document.createElement('div')
    subtitle.textContent = target.subtitle
    content.append(title, subtitle)
    const popup = L.popup({ offset: [0, -6] }).setLatLng([target.lat, target.lng]).setContent(content).openOn(map)
    return () => {
      popup.remove()
    }
  }, [map, target])
  return null
}
