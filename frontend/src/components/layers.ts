// One definition of each map layer's look, shared by the map, the toggles and the list.

export type LayerKey = 'discovered' | 'portfolio_inside' | 'portfolio_outside' | 'matched'

export interface LayerStyle {
  label: string
  description: string
  color: string
  fill: string
  radius: number
  dash?: string
  weight: number
  fillOpacity: number
}

export const LAYERS: Record<LayerKey, LayerStyle> = {
  discovered: {
    label: 'Discovered stores',
    description: 'Outlets found by the places API inside the boundary',
    color: '#0b4e43',
    fill: '#12806d',
    radius: 4.5,
    weight: 1,
    fillOpacity: 0.85,
  },
  portfolio_inside: {
    label: 'Portfolio · inside',
    description: 'Your stores within this market',
    color: '#ffffff',
    fill: '#b1306f',
    radius: 8,
    weight: 2,
    fillOpacity: 1,
  },
  portfolio_outside: {
    label: 'Portfolio · outside',
    description: 'Your stores that fall outside the boundary',
    color: '#7a2e55',
    fill: '#f1d9e5',
    radius: 7,
    weight: 2.5,
    dash: '3 2',
    fillOpacity: 1,
  },
  matched: {
    label: 'Matched',
    description: 'Portfolio stores with a discovered store within 150 m',
    color: '#d18a00',
    fill: '#d18a00',
    radius: 14,
    weight: 3,
    fillOpacity: 0,
  },
}

export const LAYER_ORDER: LayerKey[] = ['discovered', 'portfolio_inside', 'portfolio_outside', 'matched']
