import { ApiError } from '../api/client'

export function ErrorNotice({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <div className="notice notice--error" role="alert">
      {title && <strong>{title}</strong>}
      <p>{message}</p>
      {error instanceof ApiError && error.code === 'network_error' && (
        <p className="notice__hint">Start the API with “make api” or “docker compose up”.</p>
      )}
    </div>
  )
}
