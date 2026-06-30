"""Cartera (portfolio) deterministic figures.

Policies in force, total premium, expected commission, mix by ramo/insurer,
concentration (HHI by insurer and by client), premium by segment, and growth vs
the prior snapshot. No model calls, no I/O. Missing prior snapshot -> growth is an
explicit 'sin base de comparacion' (None), never a fabricated delta.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.money import ZERO, hhi, pct_change, share, total
from nexo_os.data.schema.models import Cliente, EstadoPoliza, Poliza


@dataclass(frozen=True)
class CarteraResult:
    polizas_en_vigor: int
    prima_total: Decimal
    comision_esperada_total: Decimal
    mix_ramo: dict[str, Decimal]
    mix_aseguradora: dict[str, Decimal]
    hhi_aseguradora: float | None
    hhi_cliente: float | None
    aseguradora_dominante: str | None
    share_dominante: float
    concentracion_alerta: bool
    prima_por_segmento: dict[str, Decimal]
    crecimiento_prima: float | None
    sin_base_comparacion: bool
    segmentos_en_baja: list[tuple[str, float]] = field(default_factory=list)


def _vigentes(polizas: list[Poliza]) -> list[Poliza]:
    return [p for p in polizas if p.estado == EstadoPoliza.vigente]


def _prima_por_segmento(polizas: list[Poliza], clientes: list[Cliente]) -> dict[str, Decimal]:
    seg_by_cliente = {c.cliente_id: (c.segmento or "sin_segmento") for c in clientes}
    acc: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in _vigentes(polizas):
        seg = seg_by_cliente.get(p.cliente_id, "sin_segmento")
        acc[seg] += p.prima_ars
    return {k: total([v]) for k, v in acc.items()}


def compute_cartera(
    polizas: list[Poliza],
    clientes: list[Cliente],
    *,
    thresholds: Thresholds,
    prev_polizas: list[Poliza] | None = None,
    prev_clientes: list[Cliente] | None = None,
) -> CarteraResult:
    vig = _vigentes(polizas)
    prima_total = total([p.prima_ars for p in vig])
    comision_total = total([p.prima_ars * p.comision_pct for p in vig])

    mix_ramo: dict[str, Decimal] = defaultdict(lambda: ZERO)
    mix_aseg: dict[str, Decimal] = defaultdict(lambda: ZERO)
    por_cliente: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in vig:
        mix_ramo[str(p.ramo)] += p.prima_ars
        mix_aseg[str(p.aseguradora_id)] += p.prima_ars
        por_cliente[p.cliente_id] += p.prima_ars

    hhi_aseg = hhi(mix_aseg.values(), prima_total)
    hhi_cli = hhi(por_cliente.values(), prima_total)

    aseguradora_dominante: str | None = None
    share_dominante = 0.0
    if mix_aseg and prima_total > ZERO:
        aseguradora_dominante = max(mix_aseg, key=lambda k: mix_aseg[k])
        share_dominante = share(mix_aseg[aseguradora_dominante], prima_total)
    concentracion_alerta = (
        hhi_aseg is not None and hhi_aseg > thresholds.hhi_concentration_threshold
    )

    prima_seg = _prima_por_segmento(polizas, clientes)

    # Growth + shrinking segments vs prior snapshot.
    sin_base = prev_polizas is None
    crecimiento: float | None = None
    segmentos_en_baja: list[tuple[str, float]] = []
    if not sin_base:
        prev_prima = total([p.prima_ars for p in _vigentes(prev_polizas or [])])
        crecimiento = pct_change(prima_total, prev_prima)
        prev_seg = _prima_por_segmento(prev_polizas or [], prev_clientes or [])
        for seg, cur in prima_seg.items():
            base = prev_seg.get(seg, ZERO)
            delta = pct_change(cur, base)
            if delta is not None and delta <= thresholds.shrinking_segment_pct:
                segmentos_en_baja.append((seg, delta))

    return CarteraResult(
        polizas_en_vigor=len(vig),
        prima_total=prima_total,
        comision_esperada_total=comision_total,
        mix_ramo=dict(mix_ramo),
        mix_aseguradora=dict(mix_aseg),
        hhi_aseguradora=hhi_aseg,
        hhi_cliente=hhi_cli,
        aseguradora_dominante=aseguradora_dominante,
        share_dominante=share_dominante,
        concentracion_alerta=concentracion_alerta,
        prima_por_segmento=prima_seg,
        crecimiento_prima=crecimiento,
        sin_base_comparacion=sin_base,
        segmentos_en_baja=segmentos_en_baja,
    )
