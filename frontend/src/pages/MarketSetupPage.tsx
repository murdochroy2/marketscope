import { useMemo, useState } from 'react'
import { CircleMarker, Rectangle, Tooltip } from 'react-leaflet'
import { useNavigate, useSearchParams } from 'react-router-dom'

import {
  useCategories,
  useCities,
  useCityBoundary,
  useCountries,
  useCreateMarket,
  usePortfolioUpload,
  usePortfolioUploads,
  useStates,
} from '../api/hooks'
import type { Bounds } from '../api/types'
import { AreaMeter } from '../components/AreaMeter'
import { BaseMap } from '../components/BaseMap'
import { ErrorNotice } from '../components/ErrorNotice'
import { FitBounds } from '../components/FitBounds'
import { LAYERS } from '../components/layers'
import { RectangleEditor } from '../components/RectangleEditor'
import { plural } from '../lib/format'
import { areaSqKm, contains, heightKm, toLatLngTuple, widthKm } from '../lib/geo'

const INDIA: Bounds = { south: 7.5, west: 68.5, north: 35.5, east: 97.5 }
const NO_PORTFOLIO = 'none'

const toId = (value: string) => (value ? Number(value) : null)

export function MarketSetupPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const uploads = usePortfolioUploads()
  const [uploadChoice, setUploadChoice] = useState<string>(params.get('upload') ?? '')
  // Default to the most recent upload when none was passed in.
  const effectiveUpload = uploadChoice || (uploads.data?.[0] ? String(uploads.data[0].id) : NO_PORTFOLIO)
  const uploadId = effectiveUpload === NO_PORTFOLIO ? null : Number(effectiveUpload)
  const portfolio = usePortfolioUpload(uploadId)

  const countries = useCountries()
  const [countryChoice, setCountryChoice] = useState<number | null>(null)
  // With a single country seeded there is nothing to choose.
  const countryId = countryChoice ?? (countries.data?.length === 1 ? countries.data[0].id : null)
  const [stateId, setStateId] = useState<number | null>(null)
  const [cityId, setCityId] = useState<number | null>(null)
  const states = useStates(countryId)
  const cities = useCities(stateId)
  const boundary = useCityBoundary(cityId)

  const categories = useCategories()
  const [categoryChoice, setCategoryChoice] = useState<Set<number> | null>(null)
  // Until the user picks, default to the categories that appear in the portfolio,
  // so discovery compares like with like.
  const categoryIds = useMemo(() => {
    if (categoryChoice) return categoryChoice
    const inPortfolio = new Set(portfolio.data?.stores.map((s) => s.category.trim().toLowerCase()))
    return new Set(categories.data?.filter((c) => inPortfolio.has(c.name.toLowerCase())).map((c) => c.id))
  }, [categoryChoice, categories.data, portfolio.data])

  // The user's rectangle only applies to the city it was drawn on. Otherwise use the server's
  // suggestion, which is centred on the city and already under the area cap.
  const [drawn, setDrawn] = useState<{ cityId: number; bounds: Bounds } | null>(null)
  const rect = drawn && drawn.cityId === cityId ? drawn.bounds : (boundary.data?.suggested ?? null)
  const setRect = (bounds: Bounds) => cityId !== null && setDrawn({ cityId, bounds })
  const [name, setName] = useState('')
  const createMarket = useCreateMarket()

  const maxArea = boundary.data?.max_area_sq_km ?? 30
  const area = rect ? areaSqKm(rect) : 0
  const overLimit = area > maxArea

  const locatedStores = useMemo(
    () => (portfolio.data?.stores ?? []).filter((s) => s.latitude !== null && s.longitude !== null),
    [portfolio.data],
  )
  const insideCount = rect
    ? locatedStores.filter((s) => contains(rect, s.latitude as number, s.longitude as number)).length
    : 0

  const blockers = [
    !cityId && 'Choose a city',
    cityId && !rect && !boundary.isError && 'Waiting for the city boundary',
    categoryIds.size === 0 && 'Select at least one category',
    overLimit && `Shrink the boundary to ${maxArea} km² or less`,
  ].filter(Boolean) as string[]

  const submit = () => {
    if (!cityId || !rect || blockers.length) return
    createMarket.mutate(
      {
        city_id: cityId,
        category_ids: [...categoryIds],
        boundary: rect,
        portfolio_upload_id: uploadId,
        name: name.trim() || undefined,
      },
      { onSuccess: (market) => navigate(`/markets/${market.id}`) },
    )
  }

  const toggleCategory = (id: number) => {
    const next = new Set(categoryIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setCategoryChoice(next)
  }

  return (
    <div className="workspace">
      <aside className="sidebar">
        <header className="page-head page-head--tight">
          <p className="eyebrow">Step 2</p>
          <h1>Set up a market</h1>
        </header>

        <fieldset className="field-group">
          <legend>Portfolio</legend>
          <label className="field" htmlFor="upload">
            <span>Compare against</span>
            <select id="upload" value={effectiveUpload} onChange={(e) => setUploadChoice(e.target.value)}>
              {uploads.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.filename} ({plural(u.row_count, 'store')})
                </option>
              ))}
              <option value={NO_PORTFOLIO}>No portfolio</option>
            </select>
          </label>
        </fieldset>

        <fieldset className="field-group">
          <legend>Location</legend>
          <label className="field" htmlFor="country">
            <span>Country</span>
            <select
              id="country"
              value={countryId ?? ''}
              onChange={(e) => {
                setCountryChoice(toId(e.target.value))
                setStateId(null)
                setCityId(null)
              }}
            >
              <option value="">Select a country</option>
              {countries.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field" htmlFor="state">
            <span>State</span>
            <select
              id="state"
              value={stateId ?? ''}
              disabled={!countryId}
              onChange={(e) => {
                setStateId(toId(e.target.value))
                setCityId(null)
              }}
            >
              <option value="">Select a state</option>
              {states.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field" htmlFor="city">
            <span>City</span>
            <select
              id="city"
              value={cityId ?? ''}
              disabled={!stateId}
              onChange={(e) => {
                setCityId(toId(e.target.value))
              }}
            >
              <option value="">Select a city</option>
              {cities.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset className="field-group">
          <legend>Store categories to discover</legend>
          <div className="chips">
            {categories.data?.map((c) => (
              <label key={c.id} className={`chip ${categoryIds.has(c.id) ? 'chip--on' : ''}`} htmlFor={`cat-${c.id}`}>
                <input
                  id={`cat-${c.id}`}
                  type="checkbox"
                  checked={categoryIds.has(c.id)}
                  onChange={() => toggleCategory(c.id)}
                />
                {c.name}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="field-group">
          <legend>Boundary</legend>
          {rect ? (
            <>
              <AreaMeter areaSqKm={area} maxSqKm={maxArea} widthKm={widthKm(rect)} heightKm={heightKm(rect)} />
              {portfolio.data && (
                <p className="muted small">
                  {insideCount} of {plural(locatedStores.length, 'located portfolio store')} inside
                  {portfolio.data.rows_missing_coordinates > 0 &&
                    `, plus ${portfolio.data.rows_missing_coordinates} to geocode`}
                </p>
              )}
              <button
                type="button"
                className="btn btn--small btn--ghost"
                onClick={() => setDrawn(null)}
              >
                Reset rectangle
              </button>
            </>
          ) : (
            <p className="muted">
              {boundary.isFetching ? 'Fetching the city boundary…' : 'Choose a city to draw its boundary.'}
            </p>
          )}
          <ErrorNotice error={boundary.error} title="Could not load the city boundary" />
        </fieldset>

        <label className="field" htmlFor="market-name">
          <span>Market name (optional)</span>
          <input
            id="market-name"
            type="text"
            maxLength={150}
            placeholder={boundary.data ? `${boundary.data.city_name} pilot` : 'e.g. Koramangala pilot'}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>

        <div className="submit-bar">
          <button
            type="button"
            className="btn btn--primary btn--block"
            disabled={blockers.length > 0 || createMarket.isPending}
            onClick={submit}
          >
            {createMarket.isPending ? 'Creating market…' : 'Create market'}
          </button>
          {blockers.length > 0 && <p className="submit-bar__reason">{blockers[0]}</p>}
          <ErrorNotice error={createMarket.error} title="Market was not created" />
        </div>
      </aside>

      <section className="map-pane">
        <BaseMap bounds={INDIA}>
          {boundary.data && (
            <>
              <FitBounds key={boundary.data.city_id} bounds={boundary.data.suggested} />
              <Rectangle
                bounds={toLatLngTuple(boundary.data.extent)}
                pathOptions={{ color: '#4b5a5c', weight: 1.5, dashArray: '6 6', fill: false }}
                interactive={false}
              />
            </>
          )}
          {locatedStores.map((s) => {
            const inside = rect ? contains(rect, s.latitude as number, s.longitude as number) : false
            const style = LAYERS[inside ? 'portfolio_inside' : 'portfolio_outside']
            return (
              <CircleMarker
                key={s.id}
                center={[s.latitude as number, s.longitude as number]}
                radius={style.radius}
                pathOptions={{
                  color: style.color,
                  fillColor: style.fill,
                  weight: style.weight,
                  fillOpacity: style.fillOpacity,
                  dashArray: style.dash,
                }}
              >
                <Tooltip>{s.store_name}</Tooltip>
              </CircleMarker>
            )
          })}
          {rect && <RectangleEditor bounds={rect} overLimit={overLimit} onChange={setRect} />}
        </BaseMap>
        {boundary.data && (
          <div className="map-legend">
            <span className="legend-dash" /> {boundary.data.city_name} extent ·{' '}
            {boundary.data.extent_area_sq_km.toLocaleString()} km²
            <span className="legend-sep" />
            Drag corners or edges to resize, the centre to move
          </div>
        )}
      </section>
    </div>
  )
}
