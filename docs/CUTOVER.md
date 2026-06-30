# Plan de corte (cutover) - reemplazar la version anterior con v3

v3 reemplaza la version anterior de Nexo. Es deliberadamente mas angosta y local
(feedback del cliente: complejidad + problemas del camino de datos en la nube). Esta
guia es el plan go/no-go para el corte.

## Diferencias que importan para el corte

- **Datos**: v3 no usa nube ni base hosteada. El insumo es un **workbook Excel** que
  el productor exporta de su gestion y sube; se valida fail-closed y se snapshotea
  en **DuckDB local**.
- **Agentes**: cinco (cartera, renovaciones, cobranza+morosidad, comisiones,
  pipeline comercial), no diez.
- **Auth**: v3 agrega login + RBAC (la version simplificada no tenia).
- **Sin ejecucion saliente**: las acciones aprobadas se **registran**; no se envia
  nada (igual que antes en este build).

## Migracion de datos / historial

- **Datos operativos** (clientes, polizas, cuotas, etc.): NO se migran desde la
  version anterior. Se cargan via la plantilla Excel (ver `docs/CARGA_DE_DATOS.md`).
  El primer upload valido crea el primer snapshot activo.
- **Aprobaciones / audit previos**: si la version anterior guardo un historial de
  aprobaciones (p.ej. `audit_log.jsonl` / `nexo_state.json` de v1), NO se mezcla en
  la cadena de hash de v3. Conservarlo **archivado** (solo lectura) como registro
  historico; v3 arranca una cadena nueva desde su primer evento.

## Pasos del corte

1. **Preparacion**
   - Desplegar v3 local (ver `docs/DEPLOYMENT.md`).
   - `make install && make bootstrap-admin`; crear los seats (admin/operador).
   - `make test && make eval` -> ambos verdes (gate).
2. **Carga inicial**
   - Exportar la cartera real a la plantilla (`make template`).
   - Subir en "Carga de datos"; corregir hasta que el informe de validacion de
     **OK**. (Recordar: la carga es todo-o-nada.)
3. **Parallel-run (1-2 ciclos)**
   - Correr el ciclo de agentes en v3 y, en paralelo, seguir operando como antes.
   - Comparar: conteos de cartera, mora por tramo, comisiones esperadas vs el
     sistema anterior y vs la planilla del productor. Las reconciliaciones internas
     deben dar OK (sin escalaciones).
   - Validar con el productor 3-5 acciones de cada agente (numeros + mensaje).
4. **Go / no-go**
   - GO si: validacion OK, `make eval` verde, reconciliaciones sin quiebres, y el
     productor confirma que los numeros y las acciones son correctos.
   - NO-GO si: cualquier numero no cuadra, una reconciliacion rompe, o falta dato
     critico -> quedarse en la version anterior, corregir, repetir el parallel-run.
5. **Corte**
   - Declarar v3 como produccion; promover la rama `v3-excel-prod` a `main`.
   - Establecer la rutina: subir el Excel actualizado por periodo, correr el ciclo,
     operar la bandeja, `make backup` y guardar la copia fuera de la maquina.
6. **Rollback**
   - v3 no modifica datos externos ni los del sistema anterior, asi que el rollback
     es operativo: volver a operar con la version anterior. El store de v3 queda
     intacto (con backup) para reintentar el corte.

## Operacion diaria (post-corte)

1. Exportar/actualizar el Excel desde la gestion -> subir (admin).
2. "Correr ciclo de agentes" en la Bandeja.
3. Revisar por prioridad: aprobar / editar / rechazar (queda auditado).
4. Ejecutar las acciones aprobadas **manualmente** (Nexo no envia nada).
5. `make backup` al cerrar la sesion; copia fuera de la maquina.
