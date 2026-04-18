import { useState, useCallback } from 'react'
import { api } from '../api/client'
import { useApi } from './useApi'
import type { Vehicle } from '../types'

interface VehicleFilter {
  status?: string
  make?: string
  yearMin?: number
  yearMax?: number
  priceMin?: number
  priceMax?: number
  page?: number
  pageSize?: number
}

interface VehicleList {
  vehicles: Vehicle[]
  total: number
  page: number
  pageSize: number
}

function buildQuery(f: VehicleFilter): string {
  const p = new URLSearchParams()
  if (f.status) p.set('status', f.status)
  if (f.make) p.set('make', f.make)
  if (f.yearMin) p.set('year_min', String(f.yearMin))
  if (f.yearMax) p.set('year_max', String(f.yearMax))
  if (f.priceMin) p.set('price_min', String(f.priceMin))
  if (f.priceMax) p.set('price_max', String(f.priceMax))
  p.set('page', String(f.page ?? 1))
  p.set('page_size', String(f.pageSize ?? 20))
  return p.toString()
}

export function useVehicles(filter: VehicleFilter = {}) {
  const query = buildQuery(filter)
  return useApi<VehicleList>(`/vehicles?${query}`, [query])
}

export function useVehicle(id: string) {
  return useApi<Vehicle>(`/vehicles/${id}`, [id])
}

export function useVehicleMutations() {
  const [loading, setLoading] = useState(false)

  const createVehicle = useCallback(async (data: Partial<Vehicle>) => {
    setLoading(true)
    try {
      return await api.post<Vehicle>('/vehicles', data)
    } finally {
      setLoading(false)
    }
  }, [])

  const updateVehicle = useCallback(async (id: string, data: Partial<Vehicle>) => {
    setLoading(true)
    try {
      return await api.put<Vehicle>(`/vehicles/${id}`, data)
    } finally {
      setLoading(false)
    }
  }, [])

  return { createVehicle, updateVehicle, loading }
}
