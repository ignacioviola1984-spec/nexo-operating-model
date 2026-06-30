# Nexo v3 - modelo operativo (como funciona)

Nexo trabaja como una **linea de produccion con controles**: el modelo de lenguaje
opera, pero hay **controles de codigo** y un **humano** en los puntos criticos. La
frontera entre lo determinístico y lo generado es la idea central.

## La frontera: numeros en codigo, prosa del modelo

```
            DETERMINISTICO (codigo)                 |   MODELO (solo prosa)
  ---------------------------------------------------+--------------------------
  ingesta -> snapshot -> core (cada cifra)           |
   -> propose (confianza, prioridad, rationale)      |  narrate(result, accion)
   -> reconciliaciones                               |   redacta el mensaje ES
   -> persistencia + audit + HITL                    |   con guard de grounding
```

- **Core** (`nexo_os/core/`): funciones puras sobre objetos tipados, `Decimal`
  para dinero, sin I/O salvo el repositorio, sin llamadas al modelo. Es el unico
  lugar donde nace un numero. Tests golden contra `GROUND_TRUTH.md`.
- **Agentes** (`compute -> propose -> narrate`): `compute` y `propose` son
  deterministicos (confianza y prioridad por formula, §11). `narrate` es la unica
  parte que llama al modelo, y solo redacta prosa.
- **Guard de grounding** (`agents/narrate.py`): toda cifra del texto del modelo
  debe coincidir exactamente con un valor del `rationale` de esa accion; si
  aparece un numero inventado/redondeado, se rechaza la prosa y se usa la
  plantilla determinística. Es el muro del no-negociable #1.

## El ciclo (orchestrator)

1. Cargar el repositorio del **snapshot activo** (define la fecha as-of; sin
   `now()` disperso).
2. Cada agente `compute` (via core) en orden de valor de accion (cobranza y
   renovaciones primero).
3. `propose`: cifras -> acciones con confianza/prioridad/rationale deterministicos.
4. **Reconciliaciones** (`reliability.py`): cartera<->comisiones (prima y base),
   buckets de cobranza, subset de renovaciones. Un quiebre fuera de tolerancia ->
   se marca la corrida `con_warnings` y se escala; nunca se suaviza en silencio.
5. `narrate` (modelo) con guard de grounding -> mensaje en espanol.
6. Persistir `acciones`, `agent_runs`, `audit_log`; devolver el `NexoContext`.
7. Estado de corrida: `ok | con_warnings | error`. Ante una excepcion, la corrida
   reporta `error`; no emite numeros parciales como completos (falla cerrado).

## Maker-checker (HITL)

Toda accion nace `propuesta`. El productor la resuelve en la **Bandeja**:
`aprobada | editada | rechazada`. Cada decision registra usuario + timestamp en la
fila y en el **audit log encadenado por hash**. Aprobar **registra** la decision;
no envia nada (el seam de ejecucion es `NoopExecutionAdapter`, deshabilitado).

## Confianza y prioridad (deterministicas, §11)

- **Confianza** (0-1) = `W_DATA·completitud_de_datos + W_SIGNAL·fuerza_de_senal`.
  Nunca la produce el modelo.
- **Prioridad** (alta/media/baja) = combinacion del **monto en juego** y la
  **urgencia** (vencimiento/antiguedad). Cuando no hay monto natural,
  `monto_en_juego_ars` es nulo y se usa una rama **solo-urgencia**; nunca se
  sustituye ni infiere un monto.

## Datos y trazabilidad

Una sola frontera de datos (`NexoRepository`); agentes y core nunca leen un archivo
ni corren una query directo. El snapshot activo es inmutable; subir un workbook
valido lo archiva y crea uno nuevo. Aging y `diferencia_ars` se calculan a la
lectura contra la fecha del snapshot (nunca se almacenan), asi nunca discrepan.

Ver [README.md](README.md) para correrlo y [SECURITY.md](SECURITY.md) para datos,
PII, backups y auditoria.
