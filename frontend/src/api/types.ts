// Mirrors backend/app/api/schemas.py.

export interface Bounds {
  south: number
  west: number
  north: number
  east: number
}

export interface Country {
  id: number
  name: string
  iso_code: string
}

export interface NamedRef {
  id: number
  name: string
}

export interface Category {
  id: number
  slug: string
  name: string
}

export interface CityBoundary {
  city_id: number
  city_name: string
  extent: Bounds
  extent_area_sq_km: number
  suggested: Bounds
  max_area_sq_km: number
  source: string
}

export type GeocodeStatus = 'not_needed' | 'pending' | 'succeeded' | 'failed'

export interface PortfolioStore {
  id: number
  row_number: number
  store_name: string
  address: string
  city: string
  state: string
  country: string
  category: string
  latitude: number | null
  longitude: number | null
  geocode_status: GeocodeStatus
}

export interface PortfolioUpload {
  id: number
  filename: string
  row_count: number
  rows_missing_coordinates: number
  created_at: string
}

export interface PortfolioUploadDetail extends PortfolioUpload {
  ignored_columns: string[]
  stores: PortfolioStore[]
}

export type MarketStatus =
  | 'pending'
  | 'geocoding'
  | 'discovering'
  | 'matching'
  | 'completed'
  | 'completed_with_errors'
  | 'failed'

export interface RunError {
  stage: 'geocoding' | 'discovery' | 'pipeline'
  message: string
  row?: number
  tile?: [number, number, number, number]
}

export interface DiscoveryRun {
  id: number
  provider: string
  status: string
  geocode_attempted: number
  geocode_failed: number
  tiles_planned: number
  tiles_completed: number
  tiles_failed: number
  provider_requests: number
  places_returned: number
  stores_saved: number
  budget_exhausted: boolean
  errors: RunError[]
  started_at: string
  finished_at: string | null
}

export interface Market {
  id: number
  name: string
  status: MarketStatus
  is_finished: boolean
  country: string
  state: string
  city: string
  city_id: number
  boundary: Bounds
  area_sq_km: number
  categories: Category[]
  portfolio_upload_id: number | null
  created_at: string
  run: DiscoveryRun | null
}

export interface MarketSummary {
  id: number
  name: string
  city_name: string
  status: MarketStatus
  area_sq_km: number
  discovered_count: number
  created_at: string
}

export interface CreateMarketInput {
  city_id: number
  category_ids: number[]
  boundary: Bounds
  portfolio_upload_id: number | null
  name?: string
}

export interface DiscoveredStore {
  id: number
  name: string
  category: string
  category_slug: string
  latitude: number
  longitude: number
  address: string | null
  provider: string
  provider_place_id: string
}

export type BoundaryStatus = 'inside' | 'outside' | 'unlocated'

export interface MarketPortfolioStore {
  id: number
  name: string
  category: string
  address: string
  latitude: number | null
  longitude: number | null
  boundary_status: BoundaryStatus
  geocode_status: GeocodeStatus
  geocode_error: string | null
  matched_discovered_store_id: number | null
  match_distance_m: number | null
}

export interface MarketStores {
  market_id: number
  counts: {
    discovered: number
    portfolio_inside: number
    portfolio_outside: number
    portfolio_unlocated: number
    matched: number
  }
  discovered: DiscoveredStore[]
  portfolio: MarketPortfolioStore[]
}

export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown>
}

export interface UploadRowError {
  row: number
  column: string | null
  message: string
}
