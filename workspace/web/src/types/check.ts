// Types aligned with workspace/internal/check/ Go types.
// Backend JSON field names must match exactly.

export interface VINDecodeResult {
  vin: string
  wmi?: string
  manufacturer: string
  make: string
  model?: string
  year: number
  bodyType?: string
  fuelType?: string
  engineDisplacement?: string
  driveType?: string
  countryOfManufacture: string
  plant?: string
  plantCountry?: string
  serialNumber?: string
}

export interface VehicleAlert {
  id: string
  severity: 'critical' | 'warning' | 'info'
  // Backend sends: stolen, recall_open, mileage_rollback, mileage_gap, no_insurance, exported
  type: 'stolen' | 'recall_open' | 'mileage_rollback' | 'mileage_gap' | 'no_insurance' | 'exported' | string
  title: string
  description: string
  recommendedAction?: string
  source: string
  detectedAt?: string
}

export interface InspectionRecord {
  date: string
  country: string
  center?: string
  result: 'pass' | 'fail' | 'pending' | 'advisory'
  mileageKm?: number
  nextInspectionDate?: string
}

export interface RecallEntry {
  campaignId: string
  manufacturer: string
  description: string
  affectedComponent?: string
  status: 'open' | 'completed'
  startDate: string
  completionDate?: string
  country?: string
  source?: string
}

export interface MileageRecord {
  date: string
  mileageKm: number
  source: string
  country?: string
  isAnomaly?: boolean
}

export interface MileageConsistency {
  consistent: boolean
  rollbacks: number
  highGaps: number
  note?: string
}

export interface TechnicalSpecsRecord {
  fuelType?: string
  displacementCC?: number
  powerKW?: number
  emptyWeightKg?: number
  grossWeightKg?: number
  co2GPerKm?: number
  euroNorm?: string
  bodyType?: string
  color?: string
  numberOfSeats?: number
  numberOfCylinders?: number
}

export interface CountryReport {
  country: string
  registrations: {
    date: string
    country: string
    type: 'first_registration' | 'transfer' | 'import' | 'export'
  }[]
  inspections: InspectionRecord[]
  stolenFlag: boolean
  technicalSpecs?: TechnicalSpecsRecord | null
}

// Backend can send "error" in addition to the user-facing statuses.
export type DataSourceStatus = 'success' | 'error' | 'partial' | 'unavailable' | 'requires_owner'

export interface DataSource {
  id: string
  name: string
  country: string
  status: DataSourceStatus
  note?: string
  latencyMs?: number
}

export interface PlateInfo {
  vin?: string
  plate?: string
  make?: string
  model?: string
  variant?: string
  country?: string
  source: string
  partial?: boolean
  // Technical specs — snake_case matches Go JSON tags
  fuel_type?: string
  displacement_cc?: number
  power_kw?: number
  power_cv?: number
  empty_weight_kg?: number
  gross_weight_kg?: number
  co2_g_per_km?: number
  euro_norm?: string
  body_type?: string
  transmission?: string
  engine_code?: string
  color?: string
  number_of_seats?: number
  number_of_cylinders?: number
  model_year?: number
  // Registration
  first_registration?: string
  registration_status?: string
  // Inspection
  last_inspection_date?: string
  last_inspection_result?: string
  next_inspection_date?: string
  // Mileage
  mileage_km?: number
  mileage_date?: string
  // Ownership
  previous_owners?: number
  // Other
  district?: string
  environmental_badge?: string
  fetched_at?: string
  [key: string]: unknown
}

// VehicleReport mirrors Go's VehicleReport struct.
// nil Go slices arrive as JSON null — types reflect that with | null.
export interface VehicleReport {
  vin: string
  /** Absent when VIN could not be decoded (e.g. plate-only lookups with no VIN). */
  vinDecode?: VINDecodeResult | null
  generatedAt: string
  countries?: CountryReport[] | null
  recalls: RecallEntry[] | null
  mileageHistory: MileageRecord[] | null
  mileageConsistency?: MileageConsistency | null
  alerts: VehicleAlert[] | null
  dataSources: DataSource[]
  plateInfo?: PlateInfo | null
}

export type ReportOverallStatus = 'clean' | 'attention' | 'alerts'

export type CheckErrorCode =
  | 'invalid_vin'
  | 'rate_limit'
  | 'server_error'
  | 'not_found'
  | 'plate_not_found'
  | 'plate_unavailable'

export interface CheckError {
  code: CheckErrorCode
  message: string
  /** seconds to wait before retrying (only for rate_limit) */
  retryAfterSeconds?: number
}
