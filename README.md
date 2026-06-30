# Nexo - Modelo Operativo v3 (productor de seguros, AR)

Nexo v3 es el **sistema de produccion** para una correduria de seguros en
Argentina. Reemplaza la version anterior. Es **local** (sin nube, sin base de
datos hosteada, sin internet en el camino de datos), corre **cinco agentes** que
**proponen** acciones, y un **humano aprueba** cada una antes de que se registre.
Nada se envia a sistemas externos en este build.

> Codigo, identificadores, comentarios y commits en ingles. Todo el texto de UI y
> la prosa del modelo, en espanol rioplatense. Montos en ARS.

## Los tres no-negociables

1. **Todo numero se calcula en codigo** (`nexo_os/core/`), deterministicamente y
   trazable a sus insumos. El modelo nunca produce, estima, redondea ni "completa"
   una cifra: solo rutea, prioriza y redacta prosa. Si un numero no se puede
   calcular, el sistema lo dice; no lo inventa.
2. **Humano en el ciclo en cada accion.** Los agentes proponen; una persona
   aprueba/edita/rechaza. Las decisiones quedan en un audit log inmutable.
3. **Falla cerrado.** Datos faltantes, una validacion fallida, un cross-check roto
   o baja confianza -> se marca y se detiene; nunca se adivina. Una carga de Excel
   incompleta se **rechaza entera**, nunca se ingiere a medias.

## Arquitectura en una linea

Excel subido -> **validacion fail-closed** -> snapshot inmutable en **DuckDB local**
-> los 5 agentes calculan (core) y **proponen** -> **reconciliaciones** -> el modelo
**redacta** prosa (con guard de grounding) -> **bandeja HITL** (aprobar/editar/
rechazar) -> **audit log encadenado por hash**.

```
nexo_os/
  config.py            settings + TODOS los umbrales (sin magic numbers)
  data/
    schema/            modelos pydantic + DDL DuckDB + DATA_MODEL.md (el contrato)
    repository.py      NexoRepository (unica frontera de datos)
    snapshot_repository.py   impl DuckDB (lee el snapshot activo)
    ingest.py          ingesta fail-closed (todo o nada) -> snapshot
    template.py        emite la plantilla Excel canonica
    store.py           store local + backup/restore
    synthetic/         generador + GROUND_TRUTH.md + fixtures rotos
  core/                donde vive CADA numero (Decimal, sin I/O, sin modelo)
  agents/              base + narrate (guard de grounding) + scoring + los 5 agentes
  state.py             NexoContext (estado de corrida, auditado)
  review.py            maker-checker (aprobar/editar/rechazar)
  reliability.py       reconciliaciones entre agentes
  audit.py             audit log append-only encadenado por hash
  auth.py              login bcrypt + RBAC (admin/operador)
  execution.py         seam de ejecucion DESHABILITADO (NoopExecutionAdapter)
  orchestrator.py      ciclo completo
  dashboard/           app Streamlit (login, carga, resumen, agentes, bandeja, auditoria)
  evals/run_evals.py   gate de evals (sale != 0 si falla)
```

## Correr localmente (pocos comandos)

```bash
# 1) instalar (crea .venv, instala el set bloqueado)
make install                 # Windows: ./make.ps1 install

# 2) configurar secretos
cp .env.example .env         # completar NEXO_BOOTSTRAP_ADMIN_* (y ANTHROPIC_API_KEY si se usa LLM)

# 3) primer admin + datos de demo (opcional)
make bootstrap-admin         # crea el admin inicial desde el .env
make seed                    # genera workbooks sinteticos en nexo_os/data/synthetic/

# 4) levantar el tablero local (espanol)
make run                     # => streamlit run nexo_os/dashboard/app.py
```

En el tablero: **Carga de datos** (admin) sube el `.xlsx`, ve el informe de
validacion, y si es valido pasa a ser el snapshot activo. **Bandeja de
aprobaciones**: "Correr ciclo de agentes" genera las propuestas; cada una se
aprueba/edita/rechaza. **Auditoria**: verifica la cadena de hash.

Sin LLM (por defecto, `NEXO_USE_LLM=0`): la prosa usa plantillas deterministicas;
corre offline, gratis y reproducible. Con `NEXO_USE_LLM=1` + `ANTHROPIC_API_KEY`,
Claude redacta y el guard de grounding sigue exigiendo que toda cifra este en el
rationale.

## CLI

```bash
make template                # emite la plantilla de carga en blanco
make seed                    # workbooks sinteticos + fixtures rotos
make ingest WB=ruta.xlsx     # valida + carga por linea de comandos (Win: ./make.ps1 ingest ruta.xlsx)
make bootstrap-admin         # provisiona el primer admin desde .env
make backup                  # respalda el store local (sistema de registro)
make restore FILE=backups/nexo-AAAAMMDD-HHMMSS.duckdb
make test                    # pytest
make eval                    # gate de evals (§16); sale != 0 si falla
make lint                    # ruff + black --check
```

## Calidad / gate

`make test` (87 tests) y `make eval` (9 suites: ingesta fail-closed, regresion de
numeros, deteccion de agentes, grounding, minimizacion de PII, falla cerrada,
reconciliacion, integridad de auditoria, frontera RBAC). Ambos deben estar verdes.

## Documentos

- [docs/CARGA_DE_DATOS.md](docs/CARGA_DE_DATOS.md) - como exportar a la plantilla.
- [nexo_os/data/schema/DATA_MODEL.md](nexo_os/data/schema/DATA_MODEL.md) - el esquema canonico.
- [SECURITY.md](SECURITY.md) - datos, PII, backups, auditoria, seam deshabilitado.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - despliegue local (maquina/servidor, Docker opcional).
- [docs/CUTOVER.md](docs/CUTOVER.md) - plan de corte desde la version anterior.
- [OPERATING-MODEL.md](OPERATING-MODEL.md) - como funciona y la frontera determinismo/HITL.
- [REUSE_NOTES.md](REUSE_NOTES.md) - que se reuso de v1.

## Alcance (a proposito)

Sin nube, sin base hosteada, sin cotizador multi-aseguradora, sin ejecucion
saliente (nada se envia), sin multi-tenant. Un solo broker, multiples seats. El
codigo v1 (modulos planos en la raiz) queda como referencia de reuso; la linea de
produccion es `nexo_os/`.
