import type { MarketStatus } from '../api/types'

export const formatArea = (sqKm: number) => `${sqKm.toFixed(1)} km²`

export const formatDistance = (m: number) => (m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`)

export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`

export const STATUS_LABEL: Record<MarketStatus, string> = {
  pending: 'Queued',
  geocoding: 'Locating portfolio',
  discovering: 'Discovering stores',
  matching: 'Matching stores',
  completed: 'Ready',
  completed_with_errors: 'Ready with gaps',
  failed: 'Failed',
}

export const storeLabel = (name: string, category: string) => name || `Unnamed ${category.toLowerCase()}`
