import { useMemo, useState } from 'react'
import { CircleMarker, Popup, Rectangle } from 'react-leaflet'
import { Link, useParams } from 'react-router-dom'

import { useMarket, useMarketStores } from '../api/hooks'
import type { Market, MarketPortfolioStore, MarketStores } from '../api/types'
import { BaseMap } from '../components/BaseMap'
import { ErrorNotice } from '../components/ErrorNotice'
import { LAYER_ORDER, LAYERS, type LayerKey, type LayerStyle } from '../components/layers'
import { type FocusTarget, MapFocus } from '../components/MapFocus'
import { formatArea, formatDistance, plural, STATUS_LABEL, storeLabel } from '../lib/format'
import { toLatLngTuple } from '../lib/geo'

export function MarketPage() {
  const marketId = Number(useParams().marketId)
  const market = useMarket(marketId)

  if (market.isPending) return <div className="page page--narrow muted">Loading market…</div>
  if (market.isError) {
    return (
      <div className="page page--narrow">
        <ErrorNotice error={market.error} title="Market unavailable" />
        <Link to="/">Back to portfolio</Link>
      </div>
    )
  }
  return <MarketView market={market.data} />
}

const ALL_VISIBLE: Visibility = { discovered: true, portfolio_inside: true, portfolio_outside: true, matched: true }

function MarketView({ market }: { market: Market }) {
  const stores = useMarketStores(market.id, market.is_finished)
  const [visibility, setVisibility] = useState<Visibility>(ALL_VISIBLE)
  const [focus, setFocus] = useState<FocusTarget | null>(null)

  return (
    <div className="workspace">
      <aside className="sidebar">
        <header className="page-head page-head--tight">
          <p className="eyebrow">
            {market.city}, {market.state}
          </p>
          <h1>{market.name}</h1>
          <div className="meta-row">
            <StatusPill market={market} />
            <span>{formatArea(market.area_sq_km)}</span>
            <span>{market.categories.map((c) => c.name).join(', ')}</span>
          </div>
        </header>

        {!market.is_finished && <Progress market={market} />}
        {market.is_finished && <RunSummary market={market} />}
        {stores.isError && <ErrorNotice error={stores.error} title="Could not load stores" />}
        {stores.data && (
          <Dashboard
            market={market}
            data={stores.data}
            visibility={visibility}
            onVisibilityChange={setVisibility}
            focusedKey={focus?.key ?? null}
            onFocus={setFocus}
          />
        )}
      </aside>

      <section className="map-pane">
        <BaseMap bounds={market.boundary}>
          <Rectangle
            bounds={toLatLngTuple(market.boundary)}
            pathOptions={{ color: '#0f6b5c', weight: 2.5, fillOpacity: 0.04 }}
            interactive={false}
          />
          {stores.data && <StoreLayers data={stores.data} visibility={visibility} />}
          <MapFocus target={focus} />
        </BaseMap>
        <div className="map-legend">Market boundary · {formatArea(market.area_sq_km)}</div>
      </section>
    </div>
  )
}

// ---------------------------------------------------------------- progress

const PHASES: { status: Market['status']; label: string }[] = [
  { status: 'geocoding', label: 'Locate portfolio stores without coordinates' },
  { status: 'discovering', label: 'Search the boundary for stores' },
  { status: 'matching', label: 'Match portfolio stores to discovered stores' },
]

function Progress({ market }: { market: Market }) {
  const run = market.run
  const current = PHASES.findIndex((p) => p.status === market.status)
  const tileTotal = run?.tiles_planned ?? 0
  const tileDone = (run?.tiles_completed ?? 0) + (run?.tiles_failed ?? 0)
  const pct = tileTotal ? Math.round((tileDone / tileTotal) * 100) : 0

  return (
    <section className="panel progress" aria-live="polite">
      <h2>Building this market</h2>
      <ol className="phases">
        {PHASES.map((phase, i) => {
          const state = current === -1 ? 'todo' : i < current ? 'done' : i === current ? 'active' : 'todo'
          return (
            <li key={phase.status} className={`phase phase--${state}`}>
              <span className="phase__dot" />
              <div>
                {phase.label}
                {phase.status === 'geocoding' && state !== 'todo' && run && (
                  <div className="muted small">{plural(run.geocode_attempted, 'address', 'addresses')} looked up</div>
                )}
                {phase.status === 'discovering' && state === 'active' && run && tileTotal > 0 && (
                  <>
                    <div className="progress-bar">
                      <div style={{ width: `${pct}%` }} />
                    </div>
                    <div className="muted small">
                      {tileDone} of {plural(tileTotal, 'area tile')} searched · {plural(run.provider_requests, 'API request')}
                      {run.tiles_failed > 0 && ` · ${run.tiles_failed} failed`}
                    </div>
                  </>
                )}
              </div>
            </li>
          )
        })}
      </ol>
      <p className="muted small">
        Public places APIs are rate limited, so this can take a minute or two. You can leave this page and come back.
      </p>
    </section>
  )
}

function StatusPill({ market }: { market: Market }) {
  const tone =
    market.status === 'completed'
      ? 'ok'
      : market.status === 'completed_with_errors'
        ? 'warn'
        : market.status === 'failed'
          ? 'bad'
          : 'pending'
  return <span className={`pill pill--${tone}`}>{STATUS_LABEL[market.status]}</span>
}

function RunSummary({ market }: { market: Market }) {
  const run = market.run
  if (!run) return null
  const gaps = run.errors.filter((e) => e.stage === 'discovery')
  const fatal = run.errors.find((e) => e.stage === 'pipeline')
  return (
    <section className="run-summary">
      <dl className="stats">
        <div>
          <dt>Source</dt>
          <dd>{run.provider === 'overpass' ? 'OpenStreetMap' : run.provider === 'google' ? 'Google Places' : 'Fixture data'}</dd>
        </div>
        <div>
          <dt>API requests</dt>
          <dd className="num">{run.provider_requests}</dd>
        </div>
        <div>
          <dt>Area tiles</dt>
          <dd className="num">
            {run.tiles_completed}/{run.tiles_planned}
          </dd>
        </div>
      </dl>
      {fatal && (
        <div className="notice notice--error">
          <strong>The pipeline stopped</strong>
          <p>{fatal.message}</p>
        </div>
      )}
      {(run.tiles_failed > 0 || run.budget_exhausted) && (
        <details className="notice notice--warn">
          <summary>
            {run.budget_exhausted
              ? 'The request budget ran out, so part of the boundary was not searched.'
              : `${plural(run.tiles_failed, 'area tile')} could not be searched after retries. Stores there may be missing.`}
          </summary>
          <ul>
            {gaps.map((e, i) => (
              <li key={i} className="small">
                {e.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- dashboard

type Visibility = Record<LayerKey, boolean>

interface ListRow {
  key: string
  layer: LayerKey
  name: string
  category: string
  detail: string | null
  lat: number | null
  lng: number | null
}

function rowsFor(data: MarketStores): ListRow[] {
  const portfolioRow = (p: MarketPortfolioStore): ListRow => ({
    key: `p-${p.id}`,
    layer: p.boundary_status === 'inside' ? 'portfolio_inside' : 'portfolio_outside',
    name: p.name,
    category: p.category,
    detail:
      p.boundary_status === 'unlocated'
        ? p.geocode_status === 'failed'
          ? 'Address could not be located'
          : 'Not in this city, so not located'
        : p.match_distance_m !== null
          ? `Matched · discovered store ${formatDistance(p.match_distance_m)} away`
          : null,
    lat: p.latitude,
    lng: p.longitude,
  })
  return [
    ...data.portfolio.map(portfolioRow),
    ...data.discovered.map<ListRow>((d) => ({
      key: `d-${d.id}`,
      layer: 'discovered',
      name: storeLabel(d.name, d.category),
      category: d.category,
      detail: d.address,
      lat: d.latitude,
      lng: d.longitude,
    })),
  ]
}

interface DashboardProps {
  market: Market
  data: MarketStores
  visibility: Visibility
  onVisibilityChange: (v: Visibility) => void
  focusedKey: string | null
  onFocus: (target: FocusTarget) => void
}

function Dashboard({ market, data, visibility, onVisibilityChange, focusedKey, onFocus }: DashboardProps) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const rows = useMemo(() => rowsFor(data), [data])

  const counts: Record<LayerKey, number> = {
    discovered: data.counts.discovered,
    portfolio_inside: data.counts.portfolio_inside,
    portfolio_outside: data.counts.portfolio_outside + data.counts.portfolio_unlocated,
    matched: data.counts.matched,
  }
  const matchedIds = new Set(data.portfolio.filter((p) => p.matched_discovered_store_id !== null).map((p) => `p-${p.id}`))

  const q = query.trim().toLowerCase()
  const visibleRows = rows.filter((r) => {
    const layerOn = visibility[r.layer] || (visibility.matched && matchedIds.has(r.key))
    return (
      layerOn &&
      (!category || r.category.toLowerCase() === category) &&
      (!q || r.name.toLowerCase().includes(q) || (r.detail ?? '').toLowerCase().includes(q))
    )
  })

  const toggle = (key: LayerKey) => onVisibilityChange({ ...visibility, [key]: !visibility[key] })

  return (
    <>
      <fieldset className="field-group">
        <legend>Map layers</legend>
        <ul className="layer-toggles">
          {LAYER_ORDER.filter((k) => k !== 'matched' || market.portfolio_upload_id !== null).map((key) => (
            <li key={key}>
              <label htmlFor={`layer-${key}`} title={LAYERS[key].description}>
                <input
                  id={`layer-${key}`}
                  type="checkbox"
                  checked={visibility[key]}
                  onChange={() => toggle(key)}
                />
                <Swatch style={LAYERS[key]} />
                <span className="layer-toggles__label">{LAYERS[key].label}</span>
                <span className="layer-toggles__count num">{counts[key].toLocaleString()}</span>
              </label>
            </li>
          ))}
        </ul>
        {data.counts.portfolio_unlocated > 0 && (
          <p className="muted small">
            {plural(data.counts.portfolio_unlocated, 'portfolio store')} could not be placed on the map and{' '}
            {data.counts.portfolio_unlocated === 1 ? 'is' : 'are'} listed under outside.
          </p>
        )}
      </fieldset>

      <section className="store-list">
        <div className="store-list__filters">
          <input
            id="store-search"
            type="search"
            placeholder="Search stores"
            aria-label="Search stores"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select id="store-category" aria-label="Filter by category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {market.categories.map((c) => (
              <option key={c.id} value={c.name.toLowerCase()}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <p className="muted small">{plural(visibleRows.length, 'store')} shown</p>
        <ul className="store-list__items">
          {visibleRows.slice(0, 500).map((r) => (
            <li key={r.key}>
              <button
                type="button"
                disabled={r.lat === null || r.lng === null}
                onClick={() =>
                  r.lat !== null &&
                  r.lng !== null &&
                  onFocus({ key: r.key, lat: r.lat, lng: r.lng, title: r.name, subtitle: r.category })
                }
                className={focusedKey === r.key ? 'is-focused' : ''}
              >
                <Swatch style={LAYERS[matchedIds.has(r.key) ? 'matched' : r.layer]} />
                <span className="store-list__text">
                  <span className="store-list__name">{r.name}</span>
                  <span className="muted small">
                    {r.category}
                    {r.detail && ` · ${r.detail}`}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        {visibleRows.length > 500 && (
          <p className="muted small">Showing the first 500. Search or filter to narrow the list.</p>
        )}
      </section>
    </>
  )
}

function Swatch({ style }: { style: LayerStyle }) {
  return (
    <span
      className="swatch"
      style={{
        background: style.fillOpacity ? style.fill : 'transparent',
        borderColor: style.color === '#ffffff' ? style.fill : style.color,
        borderStyle: style.dash ? 'dashed' : 'solid',
      }}
      aria-hidden
    />
  )
}

function StoreLayers({ data, visibility }: { data: MarketStores; visibility: Visibility }) {
  const pathOptions = (s: LayerStyle) => ({
    color: s.color,
    fillColor: s.fill,
    weight: s.weight,
    fillOpacity: s.fillOpacity,
    dashArray: s.dash,
  })
  const located = data.portfolio.filter((p) => p.latitude !== null && p.longitude !== null)

  return (
    <>
      {visibility.discovered &&
        data.discovered.map((d) => (
          <CircleMarker
            key={`d-${d.id}`}
            center={[d.latitude, d.longitude]}
            radius={LAYERS.discovered.radius}
            pathOptions={pathOptions(LAYERS.discovered)}
          >
            <Popup>
              <strong>{storeLabel(d.name, d.category)}</strong>
              <div>{d.category}</div>
              {d.address && <div className="muted">{d.address}</div>}
            </Popup>
          </CircleMarker>
        ))}
      {visibility.matched &&
        located
          .filter((p) => p.matched_discovered_store_id !== null)
          .map((p) => (
            <CircleMarker
              key={`m-${p.id}`}
              center={[p.latitude as number, p.longitude as number]}
              radius={LAYERS.matched.radius}
              pathOptions={pathOptions(LAYERS.matched)}
              interactive={false}
            />
          ))}
      {located.map((p) => {
        const layer: LayerKey = p.boundary_status === 'inside' ? 'portfolio_inside' : 'portfolio_outside'
        if (!visibility[layer]) return null
        return (
          <CircleMarker
            key={`p-${p.id}`}
            center={[p.latitude as number, p.longitude as number]}
            radius={LAYERS[layer].radius}
            pathOptions={pathOptions(LAYERS[layer])}
          >
            <Popup>
              <strong>{p.name}</strong>
              <div>
                {p.category} · your store, {p.boundary_status} the boundary
              </div>
              {p.match_distance_m !== null && <div>Discovered store {formatDistance(p.match_distance_m)} away</div>}
              {p.geocode_status === 'succeeded' && <div className="muted">Location geocoded from address</div>}
            </Popup>
          </CircleMarker>
        )
      })}
    </>
  )
}
