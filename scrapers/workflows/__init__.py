"""CARDEX orchestration army — Generals, Soldiers, and the separate Inquisition.

Layer over the existing atoms (discovery, harvester, entity_api) that runs dealers
through the five workflows (W1-W5) with binary gates, fans out per country with a
General, and re-certifies numbers through an INDEPENDENT verification chain.

  model       — pure data types (GateVerdict, DealerResult, GeneralReport, ...)
  pipeline    — run ONE dealer through W1-W5, structured result
  general     — fan out soldiers over a country's dealer queue, aggregate coverage
  inquisition — separate chain: re-count by an orthogonal path, emit trust verdicts
  army        — the Director: 6 Generals + the Inquisition, parallel/cascade
"""
