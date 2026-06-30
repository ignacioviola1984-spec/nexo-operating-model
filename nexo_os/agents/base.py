"""The agent contract (§8).

Each agent: compute(ctx) -> result (all figures via core, deterministic, no model)
-> propose(ctx, result) -> [Accion] (figures -> actions with deterministic
confianza/prioridad and a deterministic rationale_json, no model) -> narrate(...)
(the ONLY model use: writes the Spanish message given the deterministic numbers;
introduces no figure). Agents never write to external systems - propose only
creates acciones rows.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from decimal import Decimal

from nexo_os.data.schema.models import Accion, EstadoAccion, Prioridad
from nexo_os.state import NexoContext


def _json_default(o: object) -> object:
    if isinstance(o, Decimal):
        return str(o)
    return str(o)


def make_accion_id(run_id: str, agente: str, tipo_accion: str, entidad_id: str) -> str:
    return f"{run_id}:{agente}:{tipo_accion}:{entidad_id}"


def build_accion(
    ctx: NexoContext,
    *,
    agente: str,
    tipo_accion: str,
    entidad_tipo: str,
    entidad_id: str,
    prioridad: Prioridad,
    confianza: float,
    monto_en_juego_ars: Decimal | None,
    rationale: dict,
    mensaje_es: str = "",
) -> Accion:
    """Construct a proposed Accion. rationale_json holds the deterministic numbers
    the message may cite (the grounding allow-list)."""
    return Accion(
        accion_id=make_accion_id(ctx.run_id, agente, tipo_accion, entidad_id),
        agente=agente,
        tipo_accion=tipo_accion,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        prioridad=prioridad,
        confianza=confianza,
        monto_en_juego_ars=monto_en_juego_ars,
        rationale_json=json.dumps(
            rationale, sort_keys=True, default=_json_default, ensure_ascii=False
        ),
        mensaje_es=mensaje_es,
        estado=EstadoAccion.propuesta,
        creada_en=ctx.now,
        run_id=ctx.run_id,
        snapshot_id=ctx.snapshot_id,
    )


class Agent(ABC):
    """Base agent. nombre is the agent's stable key in state/audit."""

    nombre: str

    @abstractmethod
    def compute(self, ctx: NexoContext) -> object:
        """All figures via core. Deterministic, no model call."""

    @abstractmethod
    def propose(self, ctx: NexoContext, result: object) -> list[Accion]:
        """Figures -> concrete proposed actions. Deterministic, no model call."""

    @abstractmethod
    def narrate(self, ctx: NexoContext, result: object, accion: Accion) -> dict[str, str]:
        """Model prose ONLY: returns {'text', 'source'}; introduces no figure."""

    def run(self, ctx: NexoContext) -> object:
        """compute -> propose -> narrate -> persist. The orchestrator calls this."""
        result = self.compute(ctx)
        ctx.put_result(self.nombre, result)
        for accion in self.propose(ctx, result):
            drafted = self.narrate(ctx, result, accion)
            accion.mensaje_es = drafted["text"]
            ctx.add_accion(accion)
        return result
