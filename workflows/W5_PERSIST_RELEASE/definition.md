# W5 — GUARDAR Y LIBERAR

> Persiste config+receta+estado en GitHub (main) y LIBERA del disco el crudo
> regenerable. Nada vive solo en local. El dealer se reconstruye en frío desde el repo.

## Contrato
- **Input:** dealer cerrado y servido (output de W4).
- **Output:** receta + estado + ficha en git (main, pusheado); crudo pesado
  regenerable borrado del disco local; checksum del dato estructurado conservado.

## Sub-fases y átomos reales (main @ 3adc857)

1. **Persistir lo reproducible** a git:
   - `/dealers/{ISO}/{PROV}/{CIUDAD}/{cdx_code}/ficha.json` — identidad + geo + URL stock.
   - `/dealers/.../estado.json` — último gate superado, `inventory_count`, último delta.
   - `configs/dealers/{domain}.json` o `configs/families/{cms}.json` — la receta versionada.
   - `recipes/{portal}/` — receta de portal + rendimiento + fecha de validación.
2. **Liberar el crudo** — patrón `validate-and-purge` ya en el código
   (`seam.make_live_purger`, y el harvester dropea HTML/sesión por dealer con
   `gc.collect()`). Se guarda lo ESTRUCTURADO (en PG) + la receta que lo reproduce;
   se borra el HTML/cache pesado. El dato estructurado vive en PG (no es "local
   regenerable"); el crudo de scraping sí se libera según capacidad del disco.
3. **Push constante** a main (autorizado no-force, permanente). Commits atómicos,
   decisiones registradas con su porqué.

## GATE W5 (binario)
**PASA** si y solo si:
- [ ] receta + ficha + estado están en main (pusheado a origin, verificable por `git`),
- [ ] el crudo regenerable se ha liberado del disco (no acumula),
- [ ] **reconstrucción en frío**: desde el repo (receta) se vuelve a producir el
      mismo stock del dealer SIN pérdida — checksum del dato estructurado idéntico.

**NO PASA** → no se libera el crudo hasta que la reconstrucción en frío esté
probada. Nunca se borra algo que no se sabe regenerar.

## V5 — Verificador independiente
- **Reconstrucción en frío**: clonar la receta del repo en limpio, re-ejecutar
  W3 sobre el dealer, y comparar el dato estructurado resultante con el conservado
  (checksum). Si difiere → la receta no es completa → vuelve a W2.
- **Checksum del dato estructurado** conservado en `estado.json` para comparación.
- Veredicto a `verification_verdicts`.

## Frenos (gates del owner — confirmar antes de cruzar)
- Liberar crudo: reversible si está en repo; se procede. Borrado masivo de disco
  con dato no reconstruible probado = NO sin V5 en verde.
- Push a main: autorizado no-force permanente. Force-push / borrado remoto = orden
  literal del owner.
