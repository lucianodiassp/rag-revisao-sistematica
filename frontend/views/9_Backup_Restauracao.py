"""Página de backup integral e restauração protegida da instalação."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import streamlit as st

from backend.app.backup_service import (
    BACKUP_EXTENSION,
    BackupError,
    RestoreError,
    create_backup,
    default_backup_directory,
    inspect_backup,
    restore_backup,
)
from backend.app.storage_service import (
    StorageCapacityError,
    ensure_upload_allowed,
    storage_limits,
    storage_overview,
)


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _temporary_upload(data: bytes) -> Path:
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=BACKUP_EXTENSION)
    try:
        temporary.write(data)
        return Path(temporary.name)
    finally:
        temporary.close()


def _show_manifest(manifest: dict) -> None:
    counts = (manifest.get("database") or {}).get("counts") or {}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Projetos", counts.get("projects", 0))
    col2.metric("Artigos únicos", counts.get("papers", 0))
    col3.metric("PDFs", manifest.get("pdf_count", 0))
    col4.metric("Interações de agentes", counts.get("agent_interactions", 0))
    application = manifest.get("application") or {}
    application_description = (
        f"aplicação v{application.get('version')} · "
        f"{application.get('deployment_label') or application.get('deployment_profile')} · "
        f"{application.get('user_mode_label') or application.get('user_mode')} · "
        if application.get("version")
        else "aplicação anterior ao versionamento · "
    )
    st.caption(
        f"Criado em {manifest.get('created_at', 'indisponível')} · "
        f"{application_description}"
        f"formato v{manifest.get('version', '?')} · "
        + (
            "inclui a chave-mestra cifrada pelo arquivo"
            if manifest.get("includes_master_key")
            else "não inclui chave-mestra"
        )
    )


st.title("🛡️ Backup e Restauração")
st.markdown(
    "Crie uma cópia completa e portátil da instalação, incluindo banco de dados, "
    "PDFs e chave-mestra. O arquivo é protegido por senha antes de ser gravado."
)
st.warning(
    "Guarde a senha fora da aplicação. Sem ela, o backup não poderá ser aberto. "
    "O arquivo pode restaurar credenciais de API e deve ser tratado como dado sensível."
)

limits = storage_limits()
with st.expander("Capacidade do armazenamento persistente", expanded=False):
    statuses = storage_overview()
    columns = st.columns(len(statuses))
    for column, status in zip(columns, statuses):
        column.metric(status.label, _format_size(status.stored_bytes))
        column.caption(
            f"{_format_size(status.free_bytes)} livres · "
            + ("operacional" if status.healthy else "requer atenção")
        )
    st.caption(
        f"Reserva mínima: **{limits.minimum_free_mb} MB** · "
        f"limite para importar backup: **{limits.backup_upload_mb} MB**. "
        "Em produção Web, estas áreas correspondem a volumes Docker persistentes."
    )

if mensagem := st.session_state.pop("backup_restore_success", None):
    st.success(mensagem)

st.divider()
st.header("1. Criar backup completo")

with st.form("create_full_backup"):
    password = st.text_input("Senha do backup", type="password")
    password_confirmation = st.text_input("Confirme a senha", type="password")
    sensitive_ack = st.checkbox(
        "Entendo que preciso guardar a senha e proteger o arquivo gerado."
    )
    create_submitted = st.form_submit_button(
        "🔐 Criar backup criptografado", use_container_width=True
    )

if create_submitted:
    try:
        if password != password_confirmation:
            raise ValueError("A confirmação da senha não corresponde.")
        if not sensitive_ack:
            raise ValueError("Confirme o cuidado com a senha e o arquivo de backup.")
        with st.spinner("Gerando dump, conferindo arquivos e criptografando..."):
            result = create_backup(password)
        st.session_state["last_full_backup"] = str(result["path"])
        st.success(
            f"Backup concluído: {result['filename']} ({_format_size(result['size'])})."
        )
    except Exception as error:
        st.error(f"Não foi possível criar o backup: {error}")

last_backup = st.session_state.get("last_full_backup")
if last_backup and Path(last_backup).is_file():
    backup_path = Path(last_backup)
    st.info(
        f"Uma cópia local também foi preservada em `data/backups/{backup_path.name}`."
    )
    st.download_button(
        "⬇️ Baixar último backup",
        data=backup_path.read_bytes(),
        file_name=backup_path.name,
        mime="application/octet-stream",
        use_container_width=True,
    )

st.divider()
st.header("2. Validar e restaurar um backup")
st.caption(
    "A validação é somente leitura. A restauração cria primeiro um backup automático "
    "do estado atual em `data/backups/`."
)

uploaded = st.file_uploader("Arquivo .ragbackup", type=["ragbackup"])
restore_password = st.text_input("Senha do arquivo", type="password", key="restore_password")

if st.button(
    "🔎 Validar backup",
    disabled=uploaded is None or not restore_password,
    use_container_width=True,
):
    temporary_path = None
    try:
        uploaded_bytes = uploaded.getvalue()
        ensure_upload_allowed(
            len(uploaded_bytes),
            "backup",
            Path(tempfile.gettempdir()),
            overhead_factor=2,
        )
        temporary_path = _temporary_upload(uploaded_bytes)
        with st.spinner("Decifrando e verificando a integridade do manifesto..."):
            manifest = inspect_backup(temporary_path, restore_password)
        st.session_state["validated_backup"] = {
            "sha256": hashlib.sha256(uploaded_bytes).hexdigest(),
            "manifest": manifest,
        }
        st.success("Senha correta e integridade validada.")
    except Exception as error:
        st.session_state.pop("validated_backup", None)
        st.error(f"Backup inválido: {error}")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

validated = st.session_state.get("validated_backup")
current_digest = hashlib.sha256(uploaded.getvalue()).hexdigest() if uploaded else None
if validated and validated.get("sha256") == current_digest:
    _show_manifest(validated["manifest"])
    st.error(
        "A restauração substituirá o banco, os PDFs e, quando presente, a chave-mestra "
        "pelos componentes deste arquivo. Não use outras telas durante a operação."
    )
    restore_ack = st.checkbox(
        "Entendo que o estado atual será substituído após a criação do backup de recuperação."
    )
    typed_confirmation = st.text_input(
        "Digite RESTAURAR BACKUP para confirmar", key="restore_confirmation"
    )
    restore_enabled = restore_ack and typed_confirmation == "RESTAURAR BACKUP"
    if st.button(
        "♻️ Restaurar instalação",
        type="primary",
        disabled=not restore_enabled,
        use_container_width=True,
    ):
        temporary_path = None
        try:
            uploaded_bytes = uploaded.getvalue()
            ensure_upload_allowed(
                len(uploaded_bytes),
                "backup",
                Path(tempfile.gettempdir()),
                overhead_factor=3,
            )
            temporary_path = _temporary_upload(uploaded_bytes)
            with st.spinner(
                "Criando cópia de recuperação e restaurando banco, PDFs e credenciais..."
            ):
                result = restore_backup(
                    temporary_path,
                    restore_password,
                    typed_confirmation,
                )
            recovery_name = Path(result["recovery_path"]).name
            for key in (
                "active_project_id",
                "project_selector_widget",
                "relatorio_compilado",
                "validated_backup",
                "last_full_backup",
            ):
                st.session_state.pop(key, None)
            st.cache_data.clear()
            st.cache_resource.clear()
            st.session_state["backup_restore_success"] = (
                "Restauração concluída e validada. O estado anterior permanece disponível "
                f"em data/backups/{recovery_name}."
            )
            st.rerun()
        except (BackupError, RestoreError, StorageCapacityError, ValueError) as error:
            st.error(f"Não foi possível restaurar o backup: {error}")
        except Exception as error:
            st.error(f"Falha inesperada durante a restauração: {error}")
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

with st.expander("Arquivos locais de recuperação"):
    backup_directory = default_backup_directory()
    backups = sorted(
        backup_directory.glob(f"*{BACKUP_EXTENSION}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if backup_directory.is_dir() else []
    if not backups:
        st.caption("Nenhum backup local encontrado.")
    for path in backups[:20]:
        st.write(f"`{path.name}` · {_format_size(path.stat().st_size)}")
