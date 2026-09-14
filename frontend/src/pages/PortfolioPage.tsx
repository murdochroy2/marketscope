import { useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useMarkets, usePortfolioUploads, useUploadPortfolio } from '../api/hooks'
import type { PortfolioUploadDetail, UploadRowError } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { formatArea, formatDateTime, plural, STATUS_LABEL } from '../lib/format'

const REQUIRED = ['store_name', 'address', 'city', 'state', 'country', 'category']
const OPTIONAL = ['latitude', 'longitude']

export function PortfolioPage() {
  const upload = useUploadPortfolio()
  const uploads = usePortfolioUploads()
  const markets = useMarkets()
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const submit = (file: File | undefined) => {
    if (file) upload.mutate(file)
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragOver(false)
    submit(event.dataTransfer.files[0])
  }

  return (
    <div className="page page--narrow">
      <header className="page-head">
        <p className="eyebrow">Step 1</p>
        <h1>Upload your store portfolio</h1>
        <p className="lede">
          A CSV or Excel file of your own stores. Coordinates are optional: rows without them are located
          automatically when you create a market.
        </p>
      </header>

      <section
        className={`dropzone ${dragOver ? 'dropzone--over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          id="portfolio-file"
          type="file"
          accept=".csv,.xlsx"
          className="visually-hidden"
          onChange={(e) => {
            submit(e.target.files?.[0])
            e.target.value = ''
          }}
        />
        <p className="dropzone__title">{upload.isPending ? 'Checking your file…' : 'Drop a .csv or .xlsx file here'}</p>
        <button type="button" className="btn btn--primary" onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
          Choose file
        </button>
        <div className="columns-spec">
          <span>Required columns</span>
          {REQUIRED.map((c) => (
            <code key={c}>{c}</code>
          ))}
          <span>Optional</span>
          {OPTIONAL.map((c) => (
            <code key={c} className="code--optional">
              {c}
            </code>
          ))}
        </div>
      </section>

      {upload.isError && <UploadErrors error={upload.error} />}
      {upload.isSuccess && (
        <UploadResult upload={upload.data} onContinue={() => navigate(`/markets/new?upload=${upload.data.id}`)} />
      )}

      <div className="split">
        <section className="panel">
          <h2>Previous uploads</h2>
          {uploads.data?.length ? (
            <ul className="plain-list">
              {uploads.data.map((u) => (
                <li key={u.id}>
                  <div>
                    <strong>{u.filename}</strong>
                    <span className="muted">
                      {plural(u.row_count, 'store')} · {formatDateTime(u.created_at)}
                    </span>
                  </div>
                  <Link className="btn btn--small" to={`/markets/new?upload=${u.id}`}>
                    Use
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Nothing uploaded yet.</p>
          )}
        </section>
        <section className="panel">
          <h2>Recent markets</h2>
          {markets.data?.length ? (
            <ul className="plain-list">
              {markets.data.map((m) => (
                <li key={m.id}>
                  <div>
                    <Link to={`/markets/${m.id}`}>
                      <strong>{m.name}</strong>
                    </Link>
                    <span className="muted">
                      {STATUS_LABEL[m.status]} · {formatArea(m.area_sq_km)} · {plural(m.discovered_count, 'store')}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No markets yet.</p>
          )}
        </section>
      </div>
    </div>
  )
}

function UploadResult({ upload, onContinue }: { upload: PortfolioUploadDetail; onContinue: () => void }) {
  return (
    <section className="panel panel--success">
      <div className="panel__head">
        <div>
          <h2>{upload.filename} imported</h2>
          <p className="muted">
            {plural(upload.row_count, 'store')}
            {upload.rows_missing_coordinates > 0 &&
              ` · ${plural(upload.rows_missing_coordinates, 'row')} without coordinates will be geocoded`}
          </p>
          {upload.ignored_columns.length > 0 && (
            <p className="muted">Ignored extra columns: {upload.ignored_columns.join(', ')}</p>
          )}
        </div>
        <button type="button" className="btn btn--primary" onClick={onContinue}>
          Set up a market →
        </button>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Row</th>
              <th>Store</th>
              <th>Category</th>
              <th>City</th>
              <th>Coordinates</th>
            </tr>
          </thead>
          <tbody>
            {upload.stores.map((s) => (
              <tr key={s.id}>
                <td className="num">{s.row_number}</td>
                <td>
                  {s.store_name}
                  <div className="muted small">{s.address}</div>
                </td>
                <td>{s.category}</td>
                <td>{s.city}</td>
                <td className="num">
                  {s.latitude !== null && s.longitude !== null ? (
                    `${s.latitude.toFixed(4)}, ${s.longitude.toFixed(4)}`
                  ) : (
                    <span className="pill pill--pending">To geocode</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function UploadErrors({ error }: { error: unknown }) {
  if (!(error instanceof ApiError) || error.code !== 'validation_failed') {
    return <ErrorNotice error={error} title="Upload failed" />
  }
  const details = error.details as {
    file_errors: string[]
    missing_headers: string[]
    duplicate_headers: string[]
    row_errors: UploadRowError[]
    total_row_errors: number
  }
  return (
    <section className="notice notice--error" role="alert">
      <strong>The file was not imported</strong>
      <p>{error.message}</p>
      {details.missing_headers.length > 0 && (
        <p>
          Add these column headers to the first row:{' '}
          {details.missing_headers.map((h) => (
            <code key={h}>{h}</code>
          ))}
        </p>
      )}
      {details.row_errors.length > 0 && (
        <>
          <div className="table-wrap">
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Column</th>
                  <th>Problem</th>
                </tr>
              </thead>
              <tbody>
                {details.row_errors.map((e, i) => (
                  <tr key={i}>
                    <td className="num">{e.row}</td>
                    <td>{e.column ?? '—'}</td>
                    <td>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {details.total_row_errors > details.row_errors.length && (
            <p className="muted">
              Showing the first {details.row_errors.length} of {details.total_row_errors} problems.
            </p>
          )}
        </>
      )}
    </section>
  )
}
