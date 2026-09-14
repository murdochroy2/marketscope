import type { Bounds } from '../api/types'

// Same constant and formula as backend/app/domain/geo.py, so the live readout and the
// server-side cap check agree to the metre.
const EARTH_RADIUS_KM = 6371.0088
const toRad = (deg: number) => (deg * Math.PI) / 180

export function areaSqKm(b: Bounds): number {
  const dLng = toRad(b.east - b.west)
  return EARTH_RADIUS_KM ** 2 * dLng * (Math.sin(toRad(b.north)) - Math.sin(toRad(b.south)))
}

export function widthKm(b: Bounds): number {
  const midLat = toRad((b.north + b.south) / 2)
  return EARTH_RADIUS_KM * toRad(b.east - b.west) * Math.cos(midLat)
}

export function heightKm(b: Bounds): number {
  return EARTH_RADIUS_KM * toRad(b.north - b.south)
}

/** Keeps south < north and west < east after a handle is dragged past its opposite edge. */
export function normalize(b: Bounds): Bounds {
  return {
    south: Math.min(b.south, b.north),
    north: Math.max(b.south, b.north),
    west: Math.min(b.west, b.east),
    east: Math.max(b.west, b.east),
  }
}

export function translate(b: Bounds, dLat: number, dLng: number): Bounds {
  return { south: b.south + dLat, north: b.north + dLat, west: b.west + dLng, east: b.east + dLng }
}

export function contains(b: Bounds, lat: number, lng: number): boolean {
  return lat >= b.south && lat <= b.north && lng >= b.west && lng <= b.east
}

export function center(b: Bounds): [number, number] {
  return [(b.south + b.north) / 2, (b.west + b.east) / 2]
}

export function toLatLngTuple(b: Bounds): [[number, number], [number, number]] {
  return [
    [b.south, b.west],
    [b.north, b.east],
  ]
}
