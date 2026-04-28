# 14 — Dev Hooks & Local Security Gates
**Estado:** ACTIVO  
**Fecha:** 2026-04-14  
**Mitiga:** R-C-05 (credential leakage via git push accidental)

---

## pre-commit framework + gitleaks

### Por qué gitleaks
Gitleaks es un escáner open-source (MIT) de secretos en repositorios git. Detecta tokens, API keys, passwords y patrones de credentials antes de que lleguen a un commit. Es la última línea de defensa antes de que un `git push` exponga credentials en un repositorio remoto.

Casos concretos relevantes para CARDEX:
- `INSEE_TOKEN` en un archivo de prueba o log
- `KVK_API_KEY` hardcodeado en un test
- `KBO_PASS` en un script de configuración
- SSH private key committida por error

### Instalación (una vez por máquina de desarrollo)

```bash
# 1. Instalar pre-commit (Python, versión ≥3.8)
pip install pre-commit

# 2. Desde la raíz del repositorio, instalar los hooks
pre-commit install

# 3. Verificar que el hook está activo
cat .git/hooks/pre-commit  # debe mostrar el wrapper de pre-commit
```

### Uso

El hook se ejecuta automáticamente en cada `git commit`. Si gitleaks detecta un secreto:

```
[gitleaks] Detected 1 secret(s)
Secret:  'XXXXXXXXXXXXXXXX...'
RuleID:  generic-api-key
File:    discovery/internal/config/config_test.go
Line:    42
Commit:  staged

STOP. Do not commit secrets. See .gitleaks.toml for custom rules.
```

**El commit es bloqueado.** El desarrollador debe:
1. Eliminar el secreto del archivo
2. Usar una variable de entorno o un archivo `.env` en `.gitignore`
3. Volver a hacer `git add` y `git commit`

### Si necesitas hacer bypass (emergencia)

```bash
# Solo en caso de emergencia documentada. Requiere justificación en el commit message.
SKIP=gitleaks git commit -m "..."
```

Cualquier bypass debe ser registrado en el post-mortem correspondiente.

### Configuración personalizada (`.gitleaks.toml`)

Si gitleaks produce falsos positivos en tests o fixtures, crear `.gitleaks.toml` en la raíz:

```toml
[extend]
useDefault = true

[[rules]]
# Ignorar tokens de test hardcodeados en fixtures
id = "test-fixture-token"
description = "Test fixture token (not a real secret)"
regex = '''test_token_[a-z0-9]{8}'''
tags = ["test", "fixture"]
allowlist = { regexes = ['''testdata/.*'''] }
```

### Verificación manual del historial completo

Para escanear todo el historial git (no solo staged changes):

```bash
# Instalar gitleaks directamente si se necesita escanear el historial
docker run --rm -v "$(pwd)":/repo zricethezav/gitleaks:latest detect --source=/repo --verbose

# O con binario local:
gitleaks detect --source . --log-level info
```

Ejecutar este escaneo completo antes de cada push a main y antes de hacer el repositorio público.

---

## Integración con CI (complementaria)

El pre-commit hook protege localmente. Para protección en CI (en caso de bypass local), añadir al workflow de Forgejo:

```yaml
  gitleaks-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Otros hooks recomendados (futuro)

| Hook | Propósito | Repo |
|------|-----------|------|
| `golangci-lint` | Linting Go antes de commit | `dnephin/pre-commit-golang` |
| `go-vet` | `go vet ./...` en discovery | `dnephin/pre-commit-golang` |
| `trailing-whitespace` | Limpieza básica | `pre-commit/pre-commit-hooks` |
| `end-of-file-fixer` | Newline al final de archivos | `pre-commit/pre-commit-hooks` |

Añadir estos hooks cuando el volumen de commits justifique el overhead de tiempo de CI local.
