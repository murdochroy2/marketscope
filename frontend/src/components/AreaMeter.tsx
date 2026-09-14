import { formatArea } from '../lib/format'

interface Props {
  areaSqKm: number
  maxSqKm: number
  widthKm: number
  heightKm: number
}

export function AreaMeter({ areaSqKm, maxSqKm, widthKm, heightKm }: Props) {
  const over = areaSqKm > maxSqKm
  const fill = Math.min(100, (areaSqKm / maxSqKm) * 100)
  return (
    <div className={`area-meter ${over ? 'area-meter--over' : ''}`} aria-live="polite">
      <div className="area-meter__row">
        <span className="area-meter__value">{formatArea(areaSqKm)}</span>
        <span className="area-meter__cap">of {formatArea(maxSqKm)} allowed</span>
      </div>
      <div
        className="area-meter__track"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={maxSqKm}
        aria-valuenow={Number(areaSqKm.toFixed(1))}
        aria-label="Boundary area"
      >
        <div className="area-meter__fill" style={{ width: `${fill}%` }} />
      </div>
      <div className="area-meter__dims">
        {widthKm.toFixed(2)} km wide × {heightKm.toFixed(2)} km tall
      </div>
      {over && (
        <p className="area-meter__warning">
          Shrink the rectangle by {formatArea(areaSqKm - maxSqKm)} to create this market. Larger areas mean more
          places-API calls.
        </p>
      )}
    </div>
  )
}
