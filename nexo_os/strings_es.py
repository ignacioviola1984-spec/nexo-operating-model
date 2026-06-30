"""Single module for user-facing Spanish (rioplatense) UI copy.

Keeping copy here means Spanish strings are not scattered across the dashboard.
Model-generated prose is separate (the agents' messages).
"""

APP_TITLE = "Nexo - Modelo Operativo"
APP_TAGLINE = "Co-piloto local para el productor de seguros (AR)"

LOGIN_TITLE = "Iniciar sesion"
LOGIN_USER = "Usuario"
LOGIN_PASSWORD = "Contrasena"
LOGIN_BUTTON = "Ingresar"
LOGIN_ERROR = "Usuario o contrasena invalidos."
LOGOUT = "Cerrar sesion"

NAV_RESUMEN = "Resumen ejecutivo"
NAV_COBRANZA = "Cobranza y morosidad"
NAV_RENOVACIONES = "Renovaciones"
NAV_COMISIONES = "Comisiones"
NAV_CARTERA = "Cartera"
NAV_COMERCIAL = "Pipeline comercial"
NAV_CARGA = "Carga de datos"
NAV_BANDEJA = "Bandeja de aprobaciones"
NAV_AUDITORIA = "Auditoria"

SNAPSHOT_FECHA = "Snapshot activo (fecha as-of)"
SIN_SNAPSHOT = "No hay datos cargados. Suba un workbook valido en 'Carga de datos'."
SIN_DATOS = "sin datos"
SIN_BASE = "sin base de comparacion"

UPLOAD_HELP = "Suba el workbook de carga operativa (.xlsx). La validacion es todo o nada."
UPLOAD_TEMPLATE = "Descargar plantilla"
UPLOAD_OK = "Archivo valido. Snapshot activo actualizado."
UPLOAD_RECHAZADO = "Archivo rechazado. No se cambio nada; el snapshot anterior sigue activo."
UPLOAD_SOLO_ADMIN = "Solo un administrador puede cargar datos."

INBOX_VACIA = "No hay acciones pendientes."
BTN_APROBAR = "Aprobar"
BTN_EDITAR = "Aprobar con edicion"
BTN_RECHAZAR = "Rechazar"
MENSAJE_PROPUESTO = "Mensaje propuesto (editable)"
NOTA_REVISOR = "Nota de decision (opcional)"
NO_ENVIA = "Aprobar registra la decision; no envia nada (sin ejecucion externa)."

CORRER_CICLO = "Correr ciclo de agentes"
AUDIT_OK = "Cadena de auditoria intacta."
AUDIT_ROTA = "ATENCION: la cadena de auditoria esta rota."

PRIORIDAD = "Prioridad"
CONFIANZA = "Confianza"
MONTO_EN_JUEGO = "Monto en juego (ARS)"
