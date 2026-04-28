import type { VehicleDossier, SectionStatus, APKEntry, OwnerEntry, MovementEntry } from '../../types/dossier'

interface Props {
  dossier: VehicleDossier
}

function statusBadge(s: SectionStatus) {
  const cfg: Record<SectionStatus, { label: string; cls: string }> = {
    full:        { label: '●',   cls: 'text-green-400' },
    partial:     { label: '◐',   cls: 'text-yellow-400' },
    unavailable: { label: '○',   cls: 'text-neutral-600' },
  }
  const { label, cls } = cfg[s]
  return <span className={`${cls} text-xs font-mono mr-1`} title={s}>{label}</span>
}

function SectionHeader({ label, status }: { label: string; status: SectionStatus }) {
  return (
    <h3 className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-neutral-400 mt-5 mb-2">
      {statusBadge(status)}{label}
    </h3>
  )
}

function Row({ label, value }: { label: string; value: string | number | undefined | null }) {
  if (value === undefined || value === null || value === '' || value === 0) return null
  return (
    <div className="flex justify-between py-0.5 border-b border-neutral-800 text-sm">
      <span className="text-neutral-400 truncate mr-4">{label}</span>
      <span className="text-neutral-100 text-right font-mono">{String(value)}</span>
    </div>
  )
}

function AlertBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-900/60 text-red-300 border border-red-700/40 mr-1 mb-1">
      ⚠ {label}
    </span>
  )
}

function NcapStars({ stars, year }: { stars: number; year?: number }) {
  return (
    <div className="flex items-center gap-1 mt-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={i < stars ? 'text-yellow-400 text-base' : 'text-neutral-700 text-base'}>★</span>
      ))}
      {year && <span className="text-neutral-500 text-xs ml-1">({year})</span>}
    </div>
  )
}

function OwnerHistoryTable({ owners }: { owners: OwnerEntry[] }) {
  if (!owners.length) return null
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-neutral-500 border-b border-neutral-800">
            <th className="text-left pb-1 pr-3">Desde</th>
            <th className="text-left pb-1 pr-3">Municipio</th>
            <th className="text-left pb-1 pr-3">Provincia</th>
            <th className="text-left pb-1 pr-3">Tiempo</th>
            <th className="text-left pb-1">Tipo</th>
          </tr>
        </thead>
        <tbody>
          {owners.map((o, i) => (
            <tr key={i} className="border-b border-neutral-800/50">
              <td className="py-0.5 pr-3 font-mono text-neutral-300">{o.date ? o.date.slice(0, 10) : '—'}</td>
              <td className="py-0.5 pr-3 text-neutral-300">{o.municipio || '—'}</td>
              <td className="py-0.5 pr-3 text-neutral-400">{o.provincia || '—'}</td>
              <td className="py-0.5 pr-3 text-neutral-400 max-w-[140px]">{o.time_in_possession || '—'}</td>
              <td className="py-0.5 text-neutral-500">{o.person_type || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MovementHistoryTable({ movements }: { movements: MovementEntry[] }) {
  if (!movements.length) return null
  const typeColor = (t: string) => {
    const l = t.toLowerCase()
    if (l.includes('transferencia')) return 'text-blue-400'
    if (l.includes('baja')) return 'text-red-400'
    return 'text-green-400'
  }
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-neutral-500 border-b border-neutral-800">
            <th className="text-left pb-1 pr-3">Tipo</th>
            <th className="text-left pb-1 pr-3">Fecha</th>
            <th className="text-left pb-1 pr-3">Municipio</th>
            <th className="text-left pb-1">Duración</th>
          </tr>
        </thead>
        <tbody>
          {movements.map((m, i) => (
            <tr key={i} className="border-b border-neutral-800/50">
              <td className={`py-0.5 pr-3 font-medium ${typeColor(m.type)}`}>{m.type}</td>
              <td className="py-0.5 pr-3 font-mono text-neutral-300">{m.date ? m.date.slice(0, 10) : '—'}</td>
              <td className="py-0.5 pr-3 text-neutral-300">{m.municipio || '—'}{m.provincia ? `, ${m.provincia}` : ''}</td>
              <td className="py-0.5 text-neutral-400">{m.duration || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function APKHistoryTable({ history }: { history: APKEntry[] }) {
  if (!history.length) return null
  return (
    <div className="mt-1 overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-neutral-500 border-b border-neutral-800">
            <th className="text-left pb-1 pr-3">Fecha</th>
            <th className="text-left pb-1 pr-3">Resultado</th>
            <th className="text-left pb-1 pr-3">Tipo</th>
            <th className="text-left pb-1">Defectos</th>
          </tr>
        </thead>
        <tbody>
          {history.map((e, i) => (
            <tr key={i} className="border-b border-neutral-800/50">
              <td className="py-0.5 pr-3 font-mono text-neutral-300">{e.date.slice(0, 10)}</td>
              <td className={`py-0.5 pr-3 font-medium ${e.result === 'pass' ? 'text-green-400' : e.result === 'fail' ? 'text-red-400' : 'text-yellow-400'}`}>
                {e.result}
              </td>
              <td className="py-0.5 pr-3 text-neutral-400">{e.inspection_type ?? e.station ?? '—'}</td>
              <td className="py-0.5 text-neutral-400">{e.defects_found ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DossierReport({ dossier }: Props) {
  const { identity, technical, dimensions, registration, ownership, legal, safety, inspections, fiscal, completeness } = dossier

  const legalAlerts: string[] = []
  if (legal.embargo_flag) legalAlerts.push('Embargo')
  if (legal.stolen_flag) legalAlerts.push('Robado')
  if (legal.precinted_flag) legalAlerts.push('Precintado')
  if (legal.open_recall) legalAlerts.push('Recall activo')
  if (legal.export_indicator) legalAlerts.push('Exportado')
  if (legal.renting_flag) legalAlerts.push('Renting')
  if (legal.temp_cancelled) legalAlerts.push('Baja temporal')
  if (legal.taxi_indicator) legalAlerts.push('Taxi')

  const infoAlerts: string[] = []
  if (legal.import_alert) infoAlerts.push('Importado')

  return (
    <div className="bg-neutral-900 rounded-xl p-5 text-sm space-y-1 max-w-2xl w-full mx-auto">

      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-2xl font-bold font-mono text-neutral-100 tracking-widest">
            {identity.plate ?? dossier.query_plate}
          </div>
          {identity.make && (
            <div className="text-neutral-300 mt-0.5">
              {identity.make} {identity.model} {identity.variant ? `· ${identity.variant}` : ''}
            </div>
          )}
        </div>
        <div className="text-right">
          <span className="text-xs text-neutral-500 uppercase">{dossier.query_country}</span>
          {registration.environmental_badge && (
            <div className="mt-1 inline-block ml-2 px-2 py-0.5 rounded font-bold text-xs bg-neutral-700 text-neutral-200">
              {registration.environmental_badge}
            </div>
          )}
        </div>
      </div>

      {/* Legal alerts — always visible when present */}
      {legalAlerts.length > 0 && (
        <div className="flex flex-wrap mt-1 mb-3">
          {legalAlerts.map(a => <AlertBadge key={a} label={a} />)}
        </div>
      )}

      {/* Identity */}
      <SectionHeader label="Identificación" status={completeness.identity} />
      <Row label="VIN" value={identity.vin} />
      <Row label="Matrícula" value={identity.plate} />
      <Row label="Marca" value={identity.make} />
      <Row label="Modelo" value={identity.model} />
      <Row label="Variante" value={identity.variant} />
      <Row label="Color" value={identity.color} />

      {/* Technical */}
      <SectionHeader label="Técnica" status={completeness.technical} />
      <Row label="Tipo vehículo" value={technical.vehicle_type} />
      <Row label="Carrocería" value={technical.body_type} />
      <Row label="Combustible" value={technical.fuel_type} />
      <Row label="Cilindrada (cc)" value={technical.displacement_cc} />
      <Row label="Potencia (kW)" value={technical.power_kw} />
      <Row label="Potencia (CV)" value={technical.power_cv} />
      <Row label="CO₂ (g/km)" value={technical.co2_g_per_km} />
      <Row label="Norma Euro" value={technical.euro_norm} />
      <Row label="Cat. homologación UE" value={technical.european_vehicle_category} />
      <Row label="Fabricante / importador" value={technical.manufacturer} />
      <Row label="Transmisión" value={technical.transmission} />
      <Row label="Plazas" value={technical.number_of_seats} />
      <Row label="Puertas" value={technical.number_of_doors} />
      <Row label="Cilindros" value={technical.number_of_cylinders} />
      <Row label="Cód. motor" value={technical.engine_code} />
      <Row label="Etiqueta energética" value={technical.energy_label} />
      {(technical.fuel_consumption_combined_l100km ?? 0) > 0 && (
        <Row label="Consumo mixto (L/100km)" value={technical.fuel_consumption_combined_l100km} />
      )}

      {/* Dimensions */}
      <SectionHeader label="Dimensiones y masa" status={completeness.dimensions} />
      <Row label="Longitud (cm)" value={dimensions.length_cm} />
      <Row label="Anchura (cm)" value={dimensions.width_cm} />
      <Row label="Altura (cm)" value={dimensions.height_cm} />
      <Row label="Batalla (cm)" value={dimensions.wheelbase_cm} />
      <Row label="Tara (kg)" value={dimensions.curb_weight_kg} />
      <Row label="MMA (kg)" value={dimensions.gross_weight_kg || dimensions.technical_max_mass_kg} />
      <Row label="Carga útil (kg)" value={dimensions.load_capacity_kg} />
      <Row label="Vel. máx (km/h)" value={dimensions.max_speed_kmh} />

      {/* Registration */}
      <SectionHeader label="Matriculación" status={completeness.registration} />
      <Row label="1ª matrícula" value={registration.first_registration ? registration.first_registration.slice(0, 10) : undefined} />
      <Row label="Última matrícula" value={registration.last_registration_date ? registration.last_registration_date.slice(0, 10) : undefined} />
      <Row label="1ª matrícula NL" value={registration.first_dutch_registration ? registration.first_dutch_registration.slice(0, 10) : undefined} />
      <Row label="Tipo matriculación" value={registration.registration_type} />
      <Row label="Procedencia" value={registration.procedencia} />
      <Row label="Antigüedad" value={registration.vehicle_age} />
      <Row label="Estado" value={registration.registration_status} />
      <Row label="País" value={registration.country} />
      <Row label="Distintivo ambiental" value={registration.environmental_badge} />
      {infoAlerts.length > 0 && (
        <div className="flex flex-wrap mt-1">
          {infoAlerts.map(a => (
            <span key={a} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-900/40 text-amber-300 border border-amber-700/40 mr-1 mb-1">
              ⚠ {a}
            </span>
          ))}
        </div>
      )}

      {/* Ownership */}
      <SectionHeader label="Titularidad" status={completeness.ownership} />
      <Row label="Nº transmisiones" value={ownership.transfer_count} />
      <Row label="Propietarios anteriores" value={ownership.previous_owners} />
      <Row label="Titular actual — municipio" value={ownership.current_owner_municipio} />
      <Row label="Titular actual — provincia" value={ownership.current_owner_provincia} />
      <Row label="Tiempo en propiedad (actual)" value={ownership.current_owner_time_in_possession} />
      <Row label="Tipo persona" value={ownership.current_owner_person_type} />
      <Row label="Último trámite" value={ownership.last_transaction_date ? ownership.last_transaction_date.slice(0, 10) : undefined} />
      <Row label="Tipo servicio" value={ownership.service_code} />

      {(ownership.owner_history?.length ?? 0) > 0 && (
        <div className="mt-2">
          <div className="text-xs text-neutral-500 mb-1">Historial de propietarios</div>
          <OwnerHistoryTable owners={ownership.owner_history!} />
        </div>
      )}

      {(ownership.movement_history?.length ?? 0) > 0 && (
        <div className="mt-3">
          <div className="text-xs text-neutral-500 mb-1">Movimientos DGT</div>
          <MovementHistoryTable movements={ownership.movement_history!} />
        </div>
      )}

      {/* Legal */}
      <SectionHeader label="Situación legal" status={completeness.legal} />
      {legalAlerts.length === 0 ? (
        completeness.legal !== 'unavailable'
          ? <div className="text-green-400 text-xs py-1">Sin alertas legales</div>
          : <div className="text-neutral-600 text-xs py-1">Sin datos disponibles</div>
      ) : null}
      {legal.cancellation_type && legal.cancellation_type !== '0' && (
        <Row label="Tipo baja" value={legal.cancellation_type} />
      )}

      {/* Safety */}
      <SectionHeader label="Seguridad" status={completeness.safety} />
      {(safety.ncap_stars ?? 0) > 0 && (
        <div className="py-1">
          <div className="text-neutral-400 text-xs mb-1">EuroNCAP</div>
          <NcapStars stars={safety.ncap_stars!} year={safety.ncap_rating_year} />
          {(safety.ncap_adult_occupant_pct ?? 0) > 0 && (
            <div className="grid grid-cols-2 gap-x-4 mt-2 text-xs text-neutral-400">
              <Row label="Adultos" value={`${safety.ncap_adult_occupant_pct?.toFixed(0)}%`} />
              <Row label="Niños" value={`${safety.ncap_child_occupant_pct?.toFixed(0)}%`} />
              <Row label="VRU" value={`${safety.ncap_vulnerable_road_user_pct?.toFixed(0)}%`} />
              <Row label="ADAS" value={`${safety.ncap_safety_assist_pct?.toFixed(0)}%`} />
            </div>
          )}
        </div>
      )}
      {(safety.eu_rapex_alerts?.length ?? 0) > 0 && (
        <div className="mt-2">
          <div className="text-red-400 text-xs mb-1">Alertas RAPEX EU ({safety.eu_rapex_alerts!.length})</div>
          {safety.eu_rapex_alerts!.map((a, i) => (
            <div key={i} className="text-xs text-neutral-400 border-b border-neutral-800 py-0.5">
              {a.brand} {a.product} — <span className="text-red-300">{a.risk_type}: {a.danger}</span>
            </div>
          ))}
        </div>
      )}

      {/* Inspections */}
      <SectionHeader label="ITV / APK" status={completeness.inspections} />
      <Row label="Última ITV" value={inspections.last_inspection_date ? inspections.last_inspection_date.slice(0, 10) : undefined} />
      <Row label="Resultado" value={inspections.last_inspection_result} />
      <Row label="Próxima ITV" value={inspections.next_inspection_date ? inspections.next_inspection_date.slice(0, 10) : undefined} />
      <Row label="Km (último registro)" value={inspections.mileage_km} />
      <Row label="Estado cuentakilómetros" value={inspections.odometer_status} />
      {(inspections.apk_history?.length ?? 0) > 0 && (
        <APKHistoryTable history={inspections.apk_history!} />
      )}

      {/* Fiscal */}
      <SectionHeader label="Fiscal / homologación" status={completeness.fiscal} />
      <Row label="BPM (NL, €)" value={fiscal.import_tax_eur} />
      <Row label="Precio catálogo (€)" value={fiscal.catalogue_price_eur} />
      <Row label="Nº homologación" value={fiscal.type_approval_number} />

      {/* Sources footer */}
      <div className="mt-5 pt-3 border-t border-neutral-800">
        <div className="text-xs text-neutral-600">
          Fuentes: {dossier.data_sources.map(s => s.name).join(' · ')}
        </div>
        <div className="text-xs text-neutral-700 mt-0.5">
          Generado: {new Date(dossier.generated_at).toLocaleString('es-ES')}
        </div>
      </div>
    </div>
  )
}
