"""Política de acesso para os perfis local e Web privado."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Mapping


ALLOWED_EMAILS_ENV = "RAG_AUTH_ALLOWED_EMAILS"
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EMAIL_SEPARATORS = re.compile(r"[,;\s]+")


class AuthConfigurationError(RuntimeError):
    """Indica uma configuração insegura ou incompleta de autenticação."""


@dataclass(frozen=True)
class AccessDecision:
    """Resultado independente da interface para uma tentativa de acesso."""

    required: bool
    authenticated: bool
    authorized: bool
    code: str
    email: str | None = None
    display_name: str | None = None
    identity_provider: str | None = None
    subject: str | None = None


def normalize_email(value) -> str:
    return str(value or "").strip().lower()


def parse_allowed_emails(value) -> tuple[str, ...]:
    """Normaliza uma lista separada por vírgula, ponto e vírgula ou espaço."""

    raw_items = _EMAIL_SEPARATORS.split(str(value or "").strip())
    emails = []
    for raw_item in raw_items:
        if not raw_item:
            continue
        email = normalize_email(raw_item)
        if not _EMAIL_PATTERN.fullmatch(email):
            raise AuthConfigurationError(
                f"E-mail inválido em {ALLOWED_EMAILS_ENV}: {raw_item!r}."
            )
        if email not in emails:
            emails.append(email)
    return tuple(emails)


def allowed_emails(environ=None) -> tuple[str, ...]:
    environment = os.environ if environ is None else environ
    return parse_allowed_emails(environment.get(ALLOWED_EMAILS_ENV, ""))


def _identity_value(identity, key, default=None):
    if identity is None:
        return default
    if isinstance(identity, Mapping):
        return identity.get(key, default)
    return getattr(identity, key, default)


def evaluate_access(
    *,
    deployment_profile: str,
    user_mode: str,
    identity=None,
    environ=None,
) -> AccessDecision:
    """Avalia o acesso sem depender do Streamlit ou do provedor OIDC."""

    if deployment_profile == "local":
        return AccessDecision(
            required=False,
            authenticated=False,
            authorized=True,
            code="local_access",
            display_name="Usuário local",
            identity_provider="local",
            subject="single-user-installation",
        )
    if deployment_profile != "web_private":
        raise AuthConfigurationError(
            f"Perfil de implantação não suportado pela autenticação: {deployment_profile!r}."
        )

    configured_emails = allowed_emails(environ)
    if not configured_emails:
        raise AuthConfigurationError(
            f"Defina {ALLOWED_EMAILS_ENV} antes de ativar o perfil Web privado."
        )
    if user_mode == "single_user" and len(configured_emails) != 1:
        raise AuthConfigurationError(
            f"O modo single_user exige exatamente um e-mail em {ALLOWED_EMAILS_ENV}."
        )

    authenticated = bool(_identity_value(identity, "is_logged_in", False))
    if not authenticated:
        return AccessDecision(
            required=True,
            authenticated=False,
            authorized=False,
            code="login_required",
        )

    email = normalize_email(_identity_value(identity, "email"))
    display_name = str(_identity_value(identity, "name") or email or "Usuário")
    if not email:
        return AccessDecision(
            required=True,
            authenticated=True,
            authorized=False,
            code="email_missing",
            display_name=display_name,
        )
    if _identity_value(identity, "email_verified") is False:
        return AccessDecision(
            required=True,
            authenticated=True,
            authorized=False,
            code="email_unverified",
            email=email,
            display_name=display_name,
        )
    if email not in configured_emails:
        return AccessDecision(
            required=True,
            authenticated=True,
            authorized=False,
            code="email_not_allowed",
            email=email,
            display_name=display_name,
        )
    identity_provider = str(_identity_value(identity, "iss") or "oidc").strip()
    subject = str(_identity_value(identity, "sub") or "").strip()
    if not subject and user_mode == "multi_user":
        return AccessDecision(
            required=True,
            authenticated=True,
            authorized=False,
            code="identity_subject_missing",
            email=email,
            display_name=display_name,
            identity_provider=identity_provider,
        )
    if not subject:
        # Compatibilidade com provedores já configurados no perfil de usuário único.
        subject = f"email:{email}"
    return AccessDecision(
        required=True,
        authenticated=True,
        authorized=True,
        code="access_granted",
        email=email,
        display_name=display_name,
        identity_provider=identity_provider,
        subject=subject,
    )
