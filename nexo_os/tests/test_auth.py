"""Phase 7: auth + RBAC + guarded dashboard actions + bootstrap admin."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from nexo_os import auth
from nexo_os.auth import AuthError
from nexo_os.config import reload_settings
from nexo_os.dashboard import actions
from nexo_os.data.schema.models import EstadoAccion, Prioridad, Rol
from nexo_os.tests.conftest import SYN

NOW = datetime(2026, 6, 30, 12, 0, 0)


def _admin(repo):
    u = auth.create_user(
        repo, usuario="admin1", nombre="Admin", rol=Rol.admin, password="secreta123", now=NOW
    )
    return auth.new_session(u, now=NOW, ttl_minutes=480)


def _operador(repo):
    u = auth.create_user(
        repo, usuario="op1", nombre="Op", rol=Rol.operador, password="clave456", now=NOW
    )
    return auth.new_session(u, now=NOW, ttl_minutes=480)


# --------------------------- password + auth -------------------------------- #
def test_password_hash_roundtrip():
    h = auth.hash_password("mi-clave")
    assert h != "mi-clave"  # never stored in plaintext
    assert auth.verify_password("mi-clave", h) is True
    assert auth.verify_password("otra", h) is False


def test_authenticate_success_and_failure(current_only_repo):
    auth.create_user(
        current_only_repo, usuario="u", nombre="U", rol=Rol.operador, password="pw", now=NOW
    )
    assert auth.authenticate(current_only_repo, "u", "pw", now=NOW).usuario == "u"
    with pytest.raises(AuthError):
        auth.authenticate(current_only_repo, "u", "mal", now=NOW)
    with pytest.raises(AuthError):
        auth.authenticate(current_only_repo, "nadie", "pw", now=NOW)


def test_login_is_audited(current_only_repo):
    auth.create_user(
        current_only_repo, usuario="u", nombre="U", rol=Rol.admin, password="pw", now=NOW
    )
    auth.authenticate(current_only_repo, "u", "pw", now=NOW)
    with pytest.raises(AuthError):
        auth.authenticate(current_only_repo, "u", "bad", now=NOW)
    logins = [e for e in current_only_repo.read_audit() if e.accion == "login"]
    assert len(logins) == 2


def test_duplicate_user_rejected(current_only_repo):
    auth.create_user(
        current_only_repo, usuario="u", nombre="U", rol=Rol.admin, password="pw", now=NOW
    )
    with pytest.raises(AuthError):
        auth.create_user(
            current_only_repo, usuario="u", nombre="U2", rol=Rol.admin, password="pw2", now=NOW
        )


# --------------------------- sessions + RBAC -------------------------------- #
def test_session_expiry_and_guards():
    sess = auth.Session(usuario="u", rol=Rol.operador, expira_en=NOW + timedelta(minutes=1))
    assert sess.is_valid(NOW) is True
    later = NOW + timedelta(minutes=2)
    with pytest.raises(AuthError):
        auth.require_authenticated(sess, now=later)  # expired
    with pytest.raises(AuthError):
        auth.require_admin(sess, now=NOW)  # operador not admin
    auth.require_authenticated(sess, now=NOW)  # ok


# --------------------------- guarded actions (RBAC eval) -------------------- #
def test_upload_requires_admin(current_only_repo):
    op = _operador(current_only_repo)
    with pytest.raises(AuthError):
        actions.do_upload(
            current_only_repo,
            op,
            SYN / "cartera_actual.xlsx",
            snapshot_fecha=date(2026, 6, 30),
            now=NOW,
        )
    with pytest.raises(AuthError):
        actions.do_upload(
            current_only_repo,
            None,
            SYN / "cartera_actual.xlsx",
            snapshot_fecha=date(2026, 6, 30),
            now=NOW,
        )


def test_admin_can_upload(tmp_path):
    from nexo_os.data.snapshot_repository import SnapshotRepository

    repo = SnapshotRepository.open(tmp_path / "n.duckdb")
    try:
        admin = _admin(repo)
        result = actions.do_upload(
            repo, admin, SYN / "cartera_actual.xlsx", snapshot_fecha=date(2026, 6, 30), now=NOW
        )
        assert result.ok
    finally:
        repo.close()


def _seed_accion(repo):
    from nexo_os.agents.base import build_accion
    from nexo_os.state import NexoContext

    snap = repo.active_snapshot()
    ctx = NexoContext(
        repo, run_id="R", snapshot_id=snap.snapshot_id, snapshot_fecha=snap.snapshot_fecha, now=NOW
    )
    a = build_accion(
        ctx,
        agente="cobranza",
        tipo_accion="gestion_cobranza",
        entidad_tipo="cuota",
        entidad_id="Q1",
        prioridad=Prioridad.alta,
        confianza=0.9,
        monto_en_juego_ars=None,
        rationale={},
        mensaje_es="x",
    )
    ctx.add_accion(a)
    return a


def test_review_actions_reject_unauthenticated(current_only_repo):
    a = _seed_accion(current_only_repo)
    for fn in (actions.do_approve, actions.do_reject):
        with pytest.raises(AuthError):
            fn(current_only_repo, None, a.accion_id, now=NOW)
    with pytest.raises(AuthError):
        actions.do_edit(current_only_repo, None, a.accion_id, "nuevo", now=NOW)


def test_operador_can_review(current_only_repo):
    op = _operador(current_only_repo)
    a = _seed_accion(current_only_repo)
    resolved = actions.do_approve(current_only_repo, op, a.accion_id, now=NOW, nota="ok")
    assert resolved.estado == EstadoAccion.aprobada
    assert resolved.resuelta_por == "op1"


# --------------------------- bootstrap -------------------------------------- #
def test_bootstrap_admin_from_env(current_only_repo, monkeypatch):
    monkeypatch.setenv("NEXO_BOOTSTRAP_ADMIN_USER", "boot")
    monkeypatch.setenv("NEXO_BOOTSTRAP_ADMIN_NAME", "Boot Admin")
    monkeypatch.setenv("NEXO_BOOTSTRAP_ADMIN_PASSWORD", "arranque123")
    s = reload_settings()
    user = auth.bootstrap_admin(current_only_repo, s, now=NOW)
    assert user.rol == Rol.admin
    # Idempotent: a second bootstrap returns the same user, not a duplicate.
    again = auth.bootstrap_admin(current_only_repo, s, now=NOW)
    assert again.usuario == "boot"
    assert len(current_only_repo.list_usuarios()) == 1
    reload_settings()


def test_bootstrap_admin_missing_config_fails(current_only_repo, monkeypatch):
    monkeypatch.delenv("NEXO_BOOTSTRAP_ADMIN_USER", raising=False)
    monkeypatch.delenv("NEXO_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    s = reload_settings()
    with pytest.raises(AuthError):
        auth.bootstrap_admin(current_only_repo, s, now=NOW)
    reload_settings()
