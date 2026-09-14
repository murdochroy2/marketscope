import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  Category,
  CityBoundary,
  Country,
  CreateMarketInput,
  Market,
  MarketStores,
  MarketSummary,
  NamedRef,
  PortfolioUpload,
  PortfolioUploadDetail,
} from './types'

const POLL_MS = 1500

export const useCountries = () =>
  useQuery({ queryKey: ['countries'], queryFn: () => api.get<Country[]>('/countries'), staleTime: Infinity })

export const useStates = (countryId: number | null) =>
  useQuery({
    queryKey: ['states', countryId],
    queryFn: () => api.get<NamedRef[]>(`/countries/${countryId}/states`),
    enabled: countryId !== null,
    staleTime: Infinity,
  })

export const useCities = (stateId: number | null) =>
  useQuery({
    queryKey: ['cities', stateId],
    queryFn: () => api.get<NamedRef[]>(`/states/${stateId}/cities`),
    enabled: stateId !== null,
    staleTime: Infinity,
  })

export const useCategories = () =>
  useQuery({ queryKey: ['categories'], queryFn: () => api.get<Category[]>('/categories'), staleTime: Infinity })

export const useCityBoundary = (cityId: number | null) =>
  useQuery({
    queryKey: ['city-boundary', cityId],
    queryFn: () => api.get<CityBoundary>(`/cities/${cityId}/boundary`),
    enabled: cityId !== null,
    staleTime: Infinity,
    retry: 1,
  })

export const usePortfolioUploads = () =>
  useQuery({ queryKey: ['portfolio-uploads'], queryFn: () => api.get<PortfolioUpload[]>('/portfolio-uploads') })

export const usePortfolioUpload = (uploadId: number | null) =>
  useQuery({
    queryKey: ['portfolio-upload', uploadId],
    queryFn: () => api.get<PortfolioUploadDetail>(`/portfolio-uploads/${uploadId}`),
    enabled: uploadId !== null,
  })

export const useUploadPortfolio = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.upload<PortfolioUploadDetail>('/portfolio-uploads', file),
    onSuccess: (upload) => {
      queryClient.setQueryData(['portfolio-upload', upload.id], upload)
      void queryClient.invalidateQueries({ queryKey: ['portfolio-uploads'] })
    },
  })
}

export const useMarkets = () =>
  useQuery({ queryKey: ['markets'], queryFn: () => api.get<MarketSummary[]>('/markets') })

export const useMarket = (marketId: number) =>
  useQuery({
    queryKey: ['market', marketId],
    queryFn: () => api.get<Market>(`/markets/${marketId}`),
    // Poll while the background pipeline runs; stop once the market reaches a final state.
    refetchInterval: (query) => (query.state.data?.is_finished ? false : POLL_MS),
  })

export const useMarketStores = (marketId: number, enabled: boolean) =>
  useQuery({
    queryKey: ['market-stores', marketId],
    queryFn: () => api.get<MarketStores>(`/markets/${marketId}/stores`),
    enabled,
  })

export const useCreateMarket = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateMarketInput) => api.post<Market>('/markets', input),
    onSuccess: (market) => {
      queryClient.setQueryData(['market', market.id], market)
      void queryClient.invalidateQueries({ queryKey: ['markets'] })
    },
  })
}
