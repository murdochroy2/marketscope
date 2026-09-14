import { describe, expect, it } from 'vitest'

import { areaSqKm, contains, heightKm, normalize, translate, widthKm } from './geo'

const bengaluru = { south: 12.8334905, west: 77.4598797, north: 13.1426196, east: 77.7840639 }

describe('areaSqKm', () => {
  it('matches the backend value for the Bengaluru extent', () => {
    // backend test_geo.py asserts 1207.4 for the same box
    expect(areaSqKm(bengaluru)).toBeCloseTo(1207.4, 0)
  })

  it('agrees with width × height for a small box', () => {
    const box = { south: 12.95, west: 77.6, north: 12.99, east: 77.65 }
    expect(areaSqKm(box)).toBeCloseTo(widthKm(box) * heightKm(box), 2)
  })

  it('is zero for a degenerate box', () => {
    expect(areaSqKm({ south: 12.9, west: 77.6, north: 12.9, east: 77.7 })).toBe(0)
  })
})

describe('normalize', () => {
  it('swaps edges that were dragged past each other', () => {
    expect(normalize({ south: 13, west: 77.7, north: 12.9, east: 77.6 })).toEqual({
      south: 12.9,
      west: 77.6,
      north: 13,
      east: 77.7,
    })
  })
})

describe('translate and contains', () => {
  it('moves a box without changing its size', () => {
    const box = { south: 12.9, west: 77.6, north: 12.95, east: 77.65 }
    const moved = translate(box, 0.01, -0.02)
    expect(areaSqKm(moved)).toBeCloseTo(areaSqKm(box), 1)
    expect(contains(moved, 12.955, 77.62)).toBe(true)
    expect(contains(moved, 12.955, 77.64)).toBe(false)
  })

  it('treats edges as inside, like the backend', () => {
    const box = { south: 12.9, west: 77.6, north: 12.95, east: 77.65 }
    expect(contains(box, 12.9, 77.6)).toBe(true)
  })
})
