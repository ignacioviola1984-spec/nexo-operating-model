# Nexo — co-piloto del productor de seguros (AR)

> **Stub de la Fase 0.** La documentación completa (qué es, cómo correrlo, el
> split determinístico/LLM y el HITL) se desarrolla en la Fase 8.

Nexo es un co-piloto de IA para **un único productor de seguros** en Argentina.
Ingiere la **cartera** del productor desde un Excel y corre agentes
especializados que **proponen acciones**. El productor **aprueba cada acción**
antes de que algo se exporte (human-in-the-loop).

Build simplificado, de un solo productor, sin multi-tenant, sin login, sin
cotizador, sin envío de mensajes. Las salidas son sólo: (a) un Excel de acciones
aprobadas y (b) una web app Streamlit con bandeja de aprobación.

## Principio de diseño

**Los números son determinísticos; la prosa es del modelo.** Toda fecha, conteo,
monto, bucket, prima, comisión, score de confianza y selección de
cliente/póliza se calcula en Python. El LLM **sólo** redacta el texto de los
mensajes y la narrativa de insights — nunca calcula ni inventa un número, fecha,
cliente o póliza.

## Cómo correr (preliminar)

```bash
pip install -r nexo/requirements.txt
python nexo/cli.py gen-data      # genera la cartera sintetica de demo
python nexo/nexo_orchestrator.py # corre el loop completo (Fase 4+)
streamlit run nexo/app.py        # bandeja de aprobacion (Fase 6+)
```

Reusa `ANTHROPIC_API_KEY` del `.env` en la raíz del repo. El core
determinístico, los tests y las evals corren **sin** API key.

## Arquitectura (espejo del modelo financiero)

| Nexo | Origen en el modelo financiero |
|------|-------------------------------|
| `cartera_core.py` | `orchestration/finance_core.py` |
| `shared_state.py` (CarteraContext) | `cfo-office/shared_state.py` (CFOContext) |
| `review.py` (single-checker) | `cfo-office/review.py` (maker-checker) |
| `nexo_orchestrator.py` | `cfo-office/cfo_orchestrator.py` |
| `app.py` | `webapp/app.py` |
