"""Deterministic synthetic data generator (`make seed`).

Builds a fully-valid workbook that conforms to the canonical template, with
planted ground-truth situations (recorded exactly in GROUND_TRUTH.md), plus
deliberately-broken fixtures so the fail-closed rejection path is tested.

All PII is visibly NON-REAL (obviously fake names, @example.com emails, invalid
document ranges) so the committed test workbook can never be mistaken for real
client data. No randomness: every figure is chosen by construction.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path

from openpyxl import Workbook

from nexo_os.data.schema.models import (
    MODEL_BY_TABLE,
    OPERATIONAL_TABLES,
    Aseguradora,
    Cliente,
    Comision,
    Cotizacion,
    Cuota,
    Lead,
    Poliza,
    Productor,
    Siniestro,
    _Row,
)

OUTDIR = Path(__file__).resolve().parent
AS_OF = date(2026, 6, 30)  # snapshot_fecha of the "current" workbook
AS_OF_PRIOR = date(2026, 5, 31)


def D(x: str | int) -> Decimal:
    return Decimal(str(x))


# --------------------------------------------------------------------------- #
# Current dataset (AS_OF 2026-06-30)
# --------------------------------------------------------------------------- #
def _productores() -> list[Productor]:
    return [
        Productor(productor_id="P1", nombre="Ana Ficticia", equipo="Equipo A", activo=True),
        Productor(productor_id="P2", nombre="Beto Ficticio", equipo="Equipo B", activo=True),
    ]


def _aseguradoras() -> list[Aseguradora]:
    terms = json.dumps({"auto": 10, "hogar": 10, "vida": 10})
    return [
        Aseguradora(
            aseguradora_id="A1", nombre="Aseguradora Norte SA", condiciones_comision_json=terms
        ),
        Aseguradora(
            aseguradora_id="A2", nombre="Aseguradora Sur SA", condiciones_comision_json=terms
        ),
        Aseguradora(
            aseguradora_id="A3", nombre="Aseguradora Este SA", condiciones_comision_json=terms
        ),
    ]


# cliente_id -> (segmento, productor)
_CLIENT_SEG = {
    "C01": ("premium", "P1"),
    "C02": ("premium", "P1"),
    "C03": ("premium", "P1"),
    "C04": ("estandar", "P1"),
    "C05": ("estandar", "P1"),
    "C06": ("estandar", "P1"),
    "C07": ("estandar", "P2"),
    "C08": ("estandar", "P2"),
    "C09": ("estandar", "P2"),
    "C10": ("estandar", "P2"),
    "C11": ("estandar", "P2"),
}


def _clientes() -> list[Cliente]:
    out = []
    for i, (cid, (seg, prod)) in enumerate(_CLIENT_SEG.items(), start=1):
        out.append(
            Cliente(
                cliente_id=cid,
                tipo="persona_fisica",
                nombre=f"Cliente Ficticio {cid}",
                documento=f"20-0000000{i}-9",  # invalid range, visibly fake
                email=f"{cid.lower()}@example.com",
                telefono=f"+54 9 11 0000-00{i:02d}",
                localidad="Ciudad Falsa",
                provincia="Buenos Aires",
                segmento=seg,
                fecha_alta=date(2024, 1, 1),
                productor_id=prod,
                estado="activo",
            )
        )
    return out


def _pol(
    pid, cliente, aseg, ramo, prima, estado, fin, *, origen=None, inicio=date(2025, 7, 1)
) -> Poliza:
    prod = _CLIENT_SEG[cliente][1]
    return Poliza(
        poliza_id=pid,
        nro_poliza=f"NRO-{pid}",
        cliente_id=cliente,
        aseguradora_id=aseg,
        ramo=ramo,
        fecha_inicio_vigencia=inicio,
        fecha_fin_vigencia=fin,
        prima_ars=D(prima),
        suma_asegurada_ars=D(prima) * 100,
        estado=estado,
        forma_pago="debito",
        frecuencia_pago="mensual",
        comision_pct=D("0.10"),
        productor_id=prod,
        poliza_origen_id=origen,
    )


def _polizas() -> list[Poliza]:
    return [
        # --- vigente (in force): total prima 1,000,000 = A1 700k / A2 200k / A3 100k
        _pol(
            "POL-EXP-07", "C01", "A1", "auto", 100000, "vigente", date(2026, 7, 10)
        ),  # <=30d, at-risk
        _pol("POL-EXP-15", "C02", "A1", "hogar", 100000, "vigente", date(2026, 7, 25)),  # <=30d
        _pol("POL-A1-a", "C03", "A1", "auto", 250000, "vigente", date(2027, 1, 31)),
        _pol("POL-A1-b", "C04", "A1", "comercio", 250000, "vigente", date(2027, 2, 28)),
        _pol("POL-EXP-45", "C05", "A2", "auto", 80000, "vigente", date(2026, 8, 14)),  # 31-60d
        _pol("POL-NEW", "C06", "A2", "vida", 60000, "vigente", date(2027, 5, 31), origen="POL-OLD"),
        _pol("POL-A2-a", "C07", "A2", "hogar", 60000, "vigente", date(2027, 3, 31)),
        _pol("POL-EXP-75", "C08", "A3", "auto", 50000, "vigente", date(2026, 9, 13)),  # 61-90d
        _pol("POL-A3-a", "C09", "A3", "vida", 50000, "vigente", date(2027, 4, 30)),
        # --- non-vigente
        _pol(
            "POL-OLD",
            "C06",
            "A2",
            "vida",
            50000,
            "renovada",
            date(2026, 5, 31),
            inicio=date(2025, 6, 1),
        ),
        _pol(
            "POL-VENC",
            "C10",
            "A3",
            "auto",
            40000,
            "vencida",
            date(2026, 3, 31),
            inicio=date(2025, 3, 1),
        ),
        _pol("POL-CANCEL", "C11", "A1", "hogar", 30000, "anulada", date(2027, 1, 1)),
    ]


def _cu(cid, poliza, nro, venc, monto, estado, *, pago=None, pagado=None) -> Cuota:
    return Cuota(
        cuota_id=cid,
        poliza_id=poliza,
        nro_cuota=nro,
        fecha_vencimiento=venc,
        monto_ars=D(monto),
        estado=estado,
        fecha_pago=pago,
        monto_pagado_ars=None if pagado is None else D(pagado),
    )


def _cuotas() -> list[Cuota]:
    return [
        # overdue (relative to AS_OF 2026-06-30), buckets with bounds (30,60,90):
        _cu("Q-130-a", "POL-A1-a", 6, date(2026, 6, 10), 10000, "pendiente"),  # 20d -> 1-30
        _cu("Q-130-b", "POL-A1-b", 6, date(2026, 6, 10), 10000, "pendiente"),  # 20d -> 1-30
        _cu("Q-3160", "POL-A2-a", 5, date(2026, 5, 15), 30000, "vencida"),  # 46d -> 31-60
        _cu("Q-6190", "POL-A3-a", 4, date(2026, 4, 20), 40000, "vencida"),  # 71d -> 61-90
        _cu("Q-90-a", "POL-EXP-07", 1, date(2026, 1, 10), 50000, "vencida"),  # 171d -> 90+
        _cu("Q-90-b", "POL-EXP-15", 1, date(2026, 1, 10), 50000, "vencida"),  # 171d -> 90+
        # not overdue:
        _cu(
            "Q-PAID",
            "POL-A1-a",
            5,
            date(2026, 5, 1),
            10000,
            "pagada",
            pago=date(2026, 4, 30),
            pagado=10000,
        ),
        _cu("Q-FUT", "POL-A1-b", 7, date(2026, 8, 1), 10000, "pendiente"),
        _cu("Q-PARC", "POL-A2-a", 6, date(2026, 8, 15), 20000, "parcial", pagado=5000),
    ]


def _com(
    cid, poliza, aseg, periodo, esperada, estado, *, base=None, liquidada=None, fliq=None
) -> Comision:
    base_v = D(base) if base is not None else D(esperada) * 10  # pct 0.10
    return Comision(
        comision_id=cid,
        poliza_id=poliza,
        aseguradora_id=aseg,
        periodo=periodo,
        base_comisionable_ars=base_v,
        comision_pct=D("0.10"),
        comision_esperada_ars=D(esperada),
        comision_liquidada_ars=None if liquidada is None else D(liquidada),
        fecha_liquidacion=fliq,
        estado=estado,
    )


def _comisiones() -> list[Comision]:
    # Current period 2026-06: base sums to 1,000,000 (ties to cartera vigente premium).
    cur = [
        _com(
            "CM-07",
            "POL-EXP-07",
            "A1",
            "2026-06",
            10000,
            "liquidada",
            liquidada=10000,
            fliq=date(2026, 6, 20),
        ),
        _com(
            "CM-15",
            "POL-EXP-15",
            "A1",
            "2026-06",
            10000,
            "liquidada",
            liquidada=10000,
            fliq=date(2026, 6, 20),
        ),
        _com(
            "CM-A1a",
            "POL-A1-a",
            "A1",
            "2026-06",
            25000,
            "con_diferencia",
            liquidada=15000,
            fliq=date(2026, 6, 20),
        ),  # diff 10k
        _com(
            "CM-A1b",
            "POL-A1-b",
            "A1",
            "2026-06",
            25000,
            "liquidada",
            liquidada=25000,
            fliq=date(2026, 6, 20),
        ),
        _com(
            "CM-45",
            "POL-EXP-45",
            "A2",
            "2026-06",
            8000,
            "liquidada",
            liquidada=8000,
            fliq=date(2026, 6, 20),
        ),
        _com(
            "CM-NEW",
            "POL-NEW",
            "A2",
            "2026-06",
            6000,
            "liquidada",
            liquidada=6000,
            fliq=date(2026, 6, 20),
        ),
        _com(
            "CM-A2a",
            "POL-A2-a",
            "A2",
            "2026-06",
            6000,
            "liquidada",
            liquidada=6000,
            fliq=date(2026, 6, 20),
        ),
        _com(
            "CM-75",
            "POL-EXP-75",
            "A3",
            "2026-06",
            5000,
            "liquidada",
            liquidada=5000,
            fliq=date(2026, 6, 20),
        ),
        _com(
            "CM-A3a", "POL-A3-a", "A3", "2026-06", 5000, "esperada", liquidada=None
        ),  # unsettled current
    ]
    # Old period 2026-03: an AGED unsettled receivable (period-end+30 = 2026-04-30).
    old = [
        _com("CM-OLD", "POL-A1-b", "A1", "2026-03", 5000, "esperada", base=50000, liquidada=None),
    ]
    return cur + old


def _leads() -> list[Lead]:
    return [
        Lead(
            lead_id="L01",
            fecha_ingreso=date(2026, 6, 1),
            nombre_prospecto="Prospecto Falso Uno",
            contacto="l01@example.com",
            canal_origen="web",
            ramo="auto",
            productor_id="P1",
            estado="nuevo",
            fecha_ultimo_movimiento=date(2026, 6, 1),
        ),  # no quote, >14d
        Lead(
            lead_id="L02",
            fecha_ingreso=date(2026, 5, 20),
            nombre_prospecto="Prospecto Falso Dos",
            contacto="l02@example.com",
            canal_origen="referido",
            ramo="hogar",
            productor_id="P1",
            estado="cotizado",
            fecha_ultimo_movimiento=date(2026, 6, 5),
        ),  # quote not presented
        Lead(
            lead_id="L03",
            fecha_ingreso=date(2026, 4, 1),
            nombre_prospecto="Prospecto Falso Tres",
            contacto="l03@example.com",
            canal_origen="redes",
            ramo="vida",
            productor_id="P2",
            estado="ganado",
            fecha_ultimo_movimiento=date(2026, 5, 1),
            fecha_cierre=date(2026, 5, 1),
            cliente_id="C03",
        ),  # won + bound
        Lead(
            lead_id="L04",
            fecha_ingreso=date(2026, 4, 10),
            nombre_prospecto="Prospecto Falso Cuatro",
            contacto="l04@example.com",
            canal_origen="llamado",
            ramo="auto",
            productor_id="P2",
            estado="perdido",
            fecha_ultimo_movimiento=date(2026, 5, 10),
            fecha_cierre=date(2026, 5, 10),
            motivo_perdida="precio",
        ),
        Lead(
            lead_id="L05",
            fecha_ingreso=date(2026, 5, 1),
            nombre_prospecto="Prospecto Falso Cinco",
            contacto="l05@example.com",
            canal_origen="web",
            ramo="comercio",
            productor_id="P1",
            estado="presentado",
            fecha_ultimo_movimiento=date(2026, 5, 20),
        ),  # aging in stage (>21d)
        Lead(
            lead_id="L06",
            fecha_ingreso=date(2026, 6, 25),
            nombre_prospecto="Prospecto Falso Seis",
            contacto="l06@example.com",
            canal_origen="referido",
            ramo="auto",
            productor_id="P2",
            estado="contactado",
            fecha_ultimo_movimiento=date(2026, 6, 26),
        ),  # recent
    ]


def _cotizaciones() -> list[Cotizacion]:
    return [
        Cotizacion(
            cotizacion_id="COT-L02",
            lead_id="L02",
            aseguradora_id="A1",
            ramo="hogar",
            prima_cotizada_ars=D(100000),
            fecha_cotizacion=date(2026, 6, 5),
            estado="emitida",
        ),
        Cotizacion(
            cotizacion_id="COT-L03",
            lead_id="L03",
            aseguradora_id="A3",
            ramo="vida",
            prima_cotizada_ars=D(150000),
            fecha_cotizacion=date(2026, 4, 20),
            estado="aceptada",
            poliza_id="POL-A3-a",
        ),  # bound (poliza_id set)
        Cotizacion(
            cotizacion_id="COT-L05",
            lead_id="L05",
            aseguradora_id="A2",
            ramo="comercio",
            prima_cotizada_ars=D(200000),
            fecha_cotizacion=date(2026, 5, 18),
            estado="presentada",
        ),
    ]


def _siniestros() -> list[Siniestro]:
    return [
        Siniestro(
            siniestro_id="SIN1",
            poliza_id="POL-EXP-07",
            fecha=date(2026, 2, 1),
            tipo="robo",
            monto_reclamado_ars=D(80000),
            monto_pagado_ars=D(60000),
            estado="pagado",
        ),
    ]


def build_current() -> dict[str, list[_Row]]:
    return {
        "clientes": _clientes(),
        "polizas": _polizas(),
        "cuotas": _cuotas(),
        "comisiones": _comisiones(),
        "leads": _leads(),
        "cotizaciones": _cotizaciones(),
        "aseguradoras": _aseguradoras(),
        "productores": _productores(),
        "siniestros": _siniestros(),
    }


def build_prior() -> dict[str, list[_Row]]:
    """Smaller valid prior snapshot (AS_OF 2026-05-31): total vigente prima 900,000,
    segment 'premium' 500,000 (shrinks to 450k = -10%), 'estandar' 400,000 (grows)."""
    clientes = [
        Cliente(
            cliente_id="C01",
            tipo="persona_fisica",
            nombre="Cliente Ficticio C01",
            documento="20-00000001-9",
            email="c01@example.com",
            segmento="premium",
            productor_id="P1",
            estado="activo",
        ),
        Cliente(
            cliente_id="C04",
            tipo="persona_fisica",
            nombre="Cliente Ficticio C04",
            documento="20-00000004-9",
            email="c04@example.com",
            segmento="estandar",
            productor_id="P1",
            estado="activo",
        ),
    ]
    polizas = [
        _pol("POLP-1", "C01", "A1", "auto", 500000, "vigente", date(2026, 12, 31)),
        _pol("POLP-2", "C04", "A2", "hogar", 400000, "vigente", date(2026, 12, 31)),
    ]
    return {
        "clientes": clientes,
        "polizas": polizas,
        "cuotas": [],
        "comisiones": [],
        "leads": [],
        "cotizaciones": [],
        "aseguradoras": _aseguradoras(),
        "productores": _productores(),
        "siniestros": [],
    }


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #
def _cell(v: object) -> object:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, Decimal):
        return float(v)
    return v


def _rows_as_dicts(dataset: dict[str, list[_Row]], table: str) -> list[dict]:
    cols = list(MODEL_BY_TABLE[table].model_fields.keys())
    return [{c: _cell(getattr(obj, c)) for c in cols} for obj in dataset.get(table, [])]


def write_workbook(
    path: Path,
    sheets: dict[str, list[dict]],
    *,
    skip: frozenset[str] = frozenset(),
) -> Path:
    """Write raw rows (dicts) to an xlsx with one sheet per operational table."""
    wb = Workbook()
    wb.remove(wb.active)
    for table in OPERATIONAL_TABLES:
        if table in skip:
            continue
        cols = list(MODEL_BY_TABLE[table].model_fields.keys())
        ws = wb.create_sheet(title=table)
        ws.append(cols)
        for row in sheets.get(table, []):
            ws.append([row.get(c) for c in cols])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _dataset_to_sheets(dataset: dict[str, list[_Row]]) -> dict[str, list[dict]]:
    return {t: _rows_as_dicts(dataset, t) for t in OPERATIONAL_TABLES}


def generate_all(outdir: Path = OUTDIR) -> dict[str, Path]:
    """Write the valid current/prior/no-siniestros workbooks + broken fixtures."""
    outdir = Path(outdir)
    current = _dataset_to_sheets(build_current())
    prior = _dataset_to_sheets(build_prior())
    written: dict[str, Path] = {}

    written["actual"] = write_workbook(outdir / "cartera_actual.xlsx", current)
    written["anterior"] = write_workbook(outdir / "cartera_anterior.xlsx", prior)
    written["sin_siniestros"] = write_workbook(
        outdir / "cartera_sin_siniestros.xlsx", current, skip=frozenset({"siniestros"})
    )

    broken_dir = outdir / "broken"
    # 1) missing required sheet (polizas)
    written["missing_sheet"] = write_workbook(
        broken_dir / "missing_sheet.xlsx", current, skip=frozenset({"polizas"})
    )
    # 2) bad enum (ramo)
    bad_enum = copy.deepcopy(current)
    bad_enum["polizas"][0]["ramo"] = "moto"
    written["bad_enum"] = write_workbook(broken_dir / "bad_enum.xlsx", bad_enum)
    # 3) broken FK (cuota -> nonexistent poliza)
    broken_fk = copy.deepcopy(current)
    broken_fk["cuotas"][0]["poliza_id"] = "NOPE"
    written["broken_fk"] = write_workbook(broken_dir / "broken_fk.xlsx", broken_fk)
    # 4) duplicate PK (two clientes with C01)
    dup_pk = copy.deepcopy(current)
    dup_pk["clientes"].append(dict(dup_pk["clientes"][0]))
    written["duplicate_pk"] = write_workbook(broken_dir / "duplicate_pk.xlsx", dup_pk)
    # 5) negative amount (prima)
    neg = copy.deepcopy(current)
    neg["polizas"][0]["prima_ars"] = -100.0
    written["negative_amount"] = write_workbook(broken_dir / "negative_amount.xlsx", neg)

    return written


def main() -> None:
    written = generate_all()
    for name, path in written.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
