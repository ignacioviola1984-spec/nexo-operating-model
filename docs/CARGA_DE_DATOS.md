# Carga de datos - como exportar desde su sistema de gestion a la plantilla

Nexo no se conecta a ningun sistema externo ni a la nube. Usted **exporta** su
cartera a la plantilla Excel de Nexo y la **sube**. La carga es **todo o nada**:
si el archivo tiene cualquier error, se rechaza completo y no se ingiere nada; el
snapshot anterior sigue activo. Corrija y vuelva a subir.

## 1. Obtener la plantilla

Descargue la plantilla en blanco desde la pantalla **Carga de datos** del tablero
(boton "Descargar plantilla"), o por linea de comandos:

```
make template            # -> nexo_os/data/templates/nexo_carga_operativa.xlsx
```

La plantilla trae una hoja por tabla, los encabezados exactos (fila 1, **no
modificar**), una hoja `instrucciones`, y listas desplegables en las columnas con
valores cerrados (estado, ramo, etc.).

## 2. Hojas y como mapear cada una

Complete una fila por registro. Las columnas derivadas (`dias_mora`,
`bucket_mora`, `diferencia_ars`) **no se cargan**: Nexo las calcula contra la
fecha del snapshot.

| Hoja | Una fila por... | Notas de mapeo |
|---|---|---|
| `clientes` | cliente | `documento` = CUIT/DNI. `estado` activo/inactivo. `productor_id` debe existir en `productores`. |
| `polizas` | poliza | `prima_ars` en ARS (sin separador de miles, punto decimal). `comision_pct` como fraccion (0.10 = 10%). `poliza_origen_id` = poliza del termino anterior si es una renovacion. `fecha_fin_vigencia` >= `fecha_inicio_vigencia`. |
| `cuotas` | cuota | `estado` pendiente/pagada/vencida/parcial. Para `parcial`, complete `monto_pagado_ars`. |
| `comisiones` | poliza x periodo | `periodo` en formato `AAAA-MM`. `comision_liquidada_ars` vacio si aun no se liquido. |
| `leads` | lead/prospecto | `estado` nuevo->...->ganado/perdido. `cliente_id` se completa cuando se gana. |
| `cotizaciones` | cotizacion | `poliza_id` se completa cuando la cotizacion se convierte en poliza emitida (bind). |
| `aseguradoras` | aseguradora | referencia. `condiciones_comision_json` opcional. |
| `productores` | productor/seat | `activo` TRUE/FALSE. |
| `siniestros` | siniestro | **OPCIONAL**. Si no la provee, el score de riesgo de renovacion se calcula sin historial de siniestros (y se aclara). |

## 3. Reglas de validacion (las mas comunes)

- **Encabezados**: no renombre ni reordene la fila 1.
- **Montos** >= 0, en ARS, punto decimal, sin separador de miles.
- **Fechas** en formato `AAAA-MM-DD`.
- **Enums** (estado, ramo, frecuencia_pago, etc.): solo los valores de la lista.
- **Integridad referencial**: todo `cliente_id`, `aseguradora_id`, `productor_id`,
  `poliza_id`, `lead_id` referenciado debe existir en su hoja.
- **Claves unicas**: no repita un id (PK) dentro de una hoja.

## 4. Subir

- En el tablero: **Carga de datos** -> subir el `.xlsx` -> se muestra el informe
  de validacion en pantalla (errores por hoja/fila/columna, o exito con conteos y
  la nueva fecha de snapshot). Solo el rol **admin** puede cargar.
- Por linea de comandos:

```
make ingest WB=ruta/al/archivo.xlsx     # (Windows) ./make.ps1 ingest ruta\al\archivo.xlsx
```

Un archivo valido pasa a ser el snapshot **activo** y archiva el anterior. Un
archivo invalido no cambia nada.

## 5. Datos de ejemplo

`make seed` genera workbooks sinteticos de prueba en `nexo_os/data/synthetic/`
(datos 100% ficticios). Sirven para ver el sistema funcionando sin datos reales.
