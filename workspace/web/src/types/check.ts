// Types for the CARDEX Check vehicle history report.

export interface VINDecodeResult {
  vin: string
  manufacturer: string
  make: string
  model: string
  year: number
  bodyType: string
  fuelType: string
  engineDisplacement?: string
  driveType?: string
  countryOfManufacture: string
  plant?: string
}

export interface VehicleAlert {
  id: string
  severity: 'critical' | 'warning' | 'info'
  type: 'stolen' | 'recall_open' | 'mileage_inconsistency' | 'total_loss' | 'other'
  title: string
  description: string
  recommendedAction: string
  source: string
  detectedAt?: string
}

export interface InspectionRecord {
  id: string
  date: string
  country: string
  center?: string
  result: 'pass' | 'fail' | 'advisory'
  mileageKm?: number
  nextInspectionDate?: string
  notes?: string
}

export interface RecallEntry {
  campaignId: string
  manufacturer: string
  description: string
  affectedComponent: string
  status: 'open' | 'completed' | 'na'
  startDate: string
  completionDate?: string
}

export interface MileageRecord {
  date: string
  mileageKm: number
  source: string
  isAnomaly?: boolean
}

export type DataSourceStatus = 'success' | 'partial' | 'unavailable' | 'requires_owner'

export interface DataSource {
  id: string
  name: string
  country: string
  status: DataSourceStatus
  recordsFound?: number
  note?: string
}

export type ReportOverallStatus = 'clean' | 'attention' | 'alerts'

export interface VehicleReport {
  vin: string
  generatedAt: string
  overallStatus: ReportOverallStatus
  vinDecode: VINDecodeResult
  alerts: VehicleAlert[]
  inspections: InspectionRecord[]
  recalls: RecallEntry[]
  mileageHistory: MileageRecord[]
  /** 0-100 consistency score; undefined if fewer than 3 mileage records */
  mileageConsistencyScore?: number
  dataSources: DataSource[]
}

export type CheckErrorCode =
  | 'invalid_vin'
  | 'rate_limit'
  | 'server_error'
  | 'not_found'

export interface CheckError {
  code: CheckErrorCode
  message: string
  /** seconds to wait before retrying (only for rate_limit) */
  retryAfterSeconds?: number
}
