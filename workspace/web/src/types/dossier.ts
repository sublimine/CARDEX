export type SectionStatus = 'full' | 'partial' | 'unavailable'

export interface DossierIdentity {
  plate?: string
  vin?: string
  make?: string
  model?: string
  variant?: string
  color?: string
}

export interface DossierTechnical {
  fuel_type?: string
  displacement_cc?: number
  power_kw?: number
  power_cv?: number
  co2_g_per_km?: number
  euro_norm?: string
  body_type?: string
  transmission?: string
  number_of_seats?: number
  number_of_doors?: number
  number_of_cylinders?: number
  engine_code?: string
  energy_label?: string
  fuel_consumption_combined_l100km?: number
  fuel_consumption_city_l100km?: number
  fuel_consumption_extra_urban_l100km?: number
}

export interface DossierDimensions {
  length_cm?: number
  width_cm?: number
  height_cm?: number
  wheelbase_cm?: number
  curb_weight_kg?: number
  gross_weight_kg?: number
  technical_max_mass_kg?: number
  load_capacity_kg?: number
  max_speed_kmh?: number
}

export interface DossierRegistration {
  first_registration?: string
  first_dutch_registration?: string
  country?: string
  registration_status?: string
  environmental_badge?: string
}

export interface DossierOwnership {
  transfer_count?: number
  previous_owners?: number
  last_transaction_date?: string
  service_code?: string
}

export interface DossierLegal {
  embargo_flag?: boolean
  stolen_flag?: boolean
  precinted_flag?: boolean
  renting_flag?: boolean
  cancellation_type?: string
  temp_cancelled?: boolean
  export_indicator?: boolean
  open_recall?: boolean
  taxi_indicator?: boolean
  has_alerts: boolean
}

export interface DossierSafety {
  ncap_stars?: number
  ncap_adult_occupant_pct?: number
  ncap_child_occupant_pct?: number
  ncap_vulnerable_road_user_pct?: number
  ncap_safety_assist_pct?: number
  ncap_rating_year?: number
  eu_rapex_alerts?: Array<{
    product?: string
    brand?: string
    category?: string
    risk_type?: string
    danger?: string
    country?: string
    alert_number?: string
    week?: string
  }>
}

export interface APKDefect {
  code: string
  count: number
  station?: string
}

export interface APKEntry {
  date: string
  result: string
  station?: string
  next_due?: string
  expiry_date?: string
  inspection_type?: string
  defects_found?: number
  defects?: APKDefect[]
}

export interface DossierInspections {
  last_inspection_date?: string
  last_inspection_result?: string
  next_inspection_date?: string
  mileage_km?: number
  mileage_date?: string
  odometer_status?: string
  apk_history?: APKEntry[]
}

export interface DossierFiscal {
  import_tax_eur?: number
  catalogue_price_eur?: number
  type_approval_number?: string
}

export interface DossierCompleteness {
  identity: SectionStatus
  technical: SectionStatus
  dimensions: SectionStatus
  registration: SectionStatus
  ownership: SectionStatus
  legal: SectionStatus
  safety: SectionStatus
  inspections: SectionStatus
  fiscal: SectionStatus
}

export interface DataSource {
  id: string
  name: string
  country: string
  status: string
}

export interface VehicleDossier {
  query_plate: string
  query_country: string
  generated_at: string

  identity: DossierIdentity
  technical: DossierTechnical
  dimensions: DossierDimensions
  registration: DossierRegistration
  ownership: DossierOwnership
  legal: DossierLegal
  safety: DossierSafety
  inspections: DossierInspections
  fiscal: DossierFiscal

  completeness: DossierCompleteness
  data_sources: DataSource[]
}
