"""Authentication + RBAC (§13).

Real login for the broker's seats: bcrypt-hashed credentials (plaintext never
stored), sessions that expire, no anonymous access. Roles: admin (uploads, user
mgmt, all views) and operador (inbox + views). First boot: bootstrap_admin
provisions one admin from .env - the single allowed bootstrap. Every login,
user-create, and the bootstrap are audited.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import bcrypt

from nexo_os import audit
from nexo_os.config import Settings
from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import Rol, Usuario


class AuthError(RuntimeError):
    """Raised on failed authentication or insufficient authorization."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_user(
    repo: NexoRepository,
    *,
    usuario: str,
    nombre: str,
    rol: Rol,
    password: str,
    now: datetime,
    actor: str = "admin",
) -> Usuario:
    if repo.get_usuario(usuario) is not None:
        raise AuthError(f"El usuario '{usuario}' ya existe.")
    if not password:
        raise AuthError("La contrasena no puede estar vacia.")
    user = Usuario(
        usuario=usuario,
        nombre=nombre,
        rol=rol,
        password_hash=hash_password(password),
        activo=True,
        creado_en=now,
    )
    repo.add_usuario(user)
    audit.record_event(
        repo,
        actor=actor,
        accion="user_create",
        ts=now,
        entidad_tipo="usuario",
        entidad_id=usuario,
        detalle={"rol": rol.value},
    )
    return user


def authenticate(repo: NexoRepository, usuario: str, password: str, *, now: datetime) -> Usuario:
    """Return the user on success; raise AuthError otherwise. Logs the attempt."""
    user = repo.get_usuario(usuario)
    ok = user is not None and user.activo and verify_password(password, user.password_hash)
    audit.record_event(
        repo,
        actor=usuario,
        accion="login",
        ts=now,
        entidad_tipo="usuario",
        entidad_id=usuario,
        detalle={"exito": bool(ok)},
    )
    if not ok:
        raise AuthError("Usuario o contrasena invalidos.")
    return user  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Sessions + RBAC
# --------------------------------------------------------------------------- #
@dataclass
class Session:
    usuario: str
    rol: Rol
    expira_en: datetime

    def is_valid(self, now: datetime) -> bool:
        return now < self.expira_en


def new_session(user: Usuario, *, now: datetime, ttl_minutes: int) -> Session:
    return Session(
        usuario=user.usuario, rol=user.rol, expira_en=now + timedelta(minutes=ttl_minutes)
    )


def require_authenticated(session: Session | None, *, now: datetime) -> Session:
    if session is None or not session.is_valid(now):
        raise AuthError("Sesion inexistente o expirada. Inicie sesion.")
    return session


def require_admin(session: Session | None, *, now: datetime) -> Session:
    s = require_authenticated(session, now=now)
    if s.rol != Rol.admin:
        raise AuthError("Accion restringida al rol admin.")
    return s


def can_upload(rol: Rol) -> bool:
    return rol == Rol.admin


def can_review(rol: Rol) -> bool:
    return rol in (Rol.admin, Rol.operador)


def bootstrap_admin(repo: NexoRepository, settings: Settings, *, now: datetime) -> Usuario:
    """Provision the initial admin from .env. The one allowed bootstrap path."""
    if not settings.bootstrap_admin_user or not settings.bootstrap_admin_password:
        raise AuthError(
            "Faltan NEXO_BOOTSTRAP_ADMIN_USER / NEXO_BOOTSTRAP_ADMIN_PASSWORD en el .env."
        )
    existing = repo.get_usuario(settings.bootstrap_admin_user)
    if existing is not None:
        return existing
    return create_user(
        repo,
        usuario=settings.bootstrap_admin_user,
        nombre=settings.bootstrap_admin_name or settings.bootstrap_admin_user,
        rol=Rol.admin,
        password=settings.bootstrap_admin_password,
        now=now,
        actor="bootstrap",
    )
