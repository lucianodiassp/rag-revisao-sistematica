"""Gestão protegida do arquivamento e da exclusão de projetos."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.app.demo_project import is_demo_project
from backend.app.project_lifecycle import (
    archive_project,
    deletion_preview,
    list_lifecycle_events,
    list_projects_for_lifecycle,
    permanently_delete_project,
    restore_project,
)
from frontend.project_selector import CHAVE_PROJETO_ATIVO


ACTION_LABELS = {
    "archived": "Arquivado",
    "restored": "Restaurado",
    "deleted": "Excluído permanentemente",
}


def _actor_identifier():
    try:
        identity = st.user.to_dict()
    except (AttributeError, KeyError):
        identity = {}
    return identity.get("email") or identity.get("name") or "operador-local"


def _format_bytes(value):
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _show_counts(preview):
    counts = preview["counts"]
    columns = st.columns(5)
    columns[0].metric("Artigos", counts["papers"])
    columns[1].metric("Buscas", counts["searches"])
    columns[2].metric("Interações", counts["interactions"])
    columns[3].metric("Tarefas", counts["jobs"])
    columns[4].metric("PDFs", preview["pdf_count"])
    st.caption(
        f"Registros recuperados: **{counts['records']}** · avaliações: "
        f"**{counts['evaluations']}** · artefatos visuais: "
        f"**{counts['visual_artifacts']}** · interpretações visuais: "
        f"**{counts['visual_interpretations']}** · espaço dos PDFs: "
        f"**{_format_bytes(preview['pdf_bytes'])}**."
    )


st.title("🗂️ Gestão de Projetos")
st.write(
    "Retire projetos do uso cotidiano sem perder dados. A exclusão permanente só "
    "fica disponível depois do arquivamento e de um novo backup completo."
)
st.info(
    "**Arquivar é reversível:** banco, PDFs, revisões e históricos permanecem intactos. "
    "Projetos arquivados deixam de aparecer no seletor das demais páginas."
)

if message := st.session_state.pop("project_lifecycle_success", None):
    st.success(message)
if warning := st.session_state.pop("project_lifecycle_warning", None):
    st.warning(warning)

projects = list_projects_for_lifecycle()
active_projects = [item for item in projects if not item.get("archived_at")]
archived_projects = [item for item in projects if item.get("archived_at")]

active_tab, archived_tab = st.tabs(
    [f"Projetos ativos ({len(active_projects)})", f"Arquivados ({len(archived_projects)})"]
)

with active_tab:
    if not active_projects:
        st.warning("Não há projetos ativos.")
    else:
        active_by_id = {item["id"]: item for item in active_projects}
        selected_active_id = st.selectbox(
            "Projeto que deseja arquivar",
            options=list(active_by_id),
            format_func=lambda item_id: active_by_id[item_id]["title"],
            key="lifecycle_active_project",
        )
        selected_active = active_by_id[selected_active_id]
        active_preview = deletion_preview(selected_active_id)
        _show_counts(active_preview)

        protected_message = active_preview.get("protected_reason")
        if not protected_message and len(active_projects) <= 1:
            protected_message = "O último projeto ativo da instalação é protegido."
        if protected_message:
            st.warning(protected_message)
        elif active_preview["counts"]["active_jobs"]:
            st.warning(
                "Este projeto possui tarefas em andamento. Aguarde a conclusão ou falha "
                "antes de arquivar."
            )

        with st.form(f"archive_project_{selected_active_id}", clear_on_submit=True):
            archive_reason = st.text_area(
                "Justificativa do arquivamento",
                placeholder="Ex.: revisão concluída e retirada da lista de trabalho ativo.",
                height=90,
            )
            archive_ack = st.checkbox(
                "Confirmo que desejo retirar este projeto do seletor operacional."
            )
            archive_submitted = st.form_submit_button(
                "📦 Arquivar projeto",
                disabled=bool(protected_message or active_preview["counts"]["active_jobs"]),
                use_container_width=True,
            )

        if archive_submitted:
            try:
                if not archive_ack:
                    raise ValueError("Confirme o arquivamento antes de continuar.")
                result = archive_project(
                    selected_active_id,
                    archive_reason,
                    actor=_actor_identifier(),
                )
            except ValueError as error:
                st.warning(str(error))
            except Exception as error:
                st.error(f"Não foi possível arquivar o projeto: {error}")
            else:
                if st.session_state.get(CHAVE_PROJETO_ATIVO) == selected_active_id:
                    st.session_state.pop(CHAVE_PROJETO_ATIVO, None)
                    st.session_state.pop("project_selector_widget", None)
                st.session_state["project_lifecycle_success"] = (
                    f"Projeto “{result['title']}” arquivado. Recibo: {result['event_id']}."
                )
                st.rerun()

with archived_tab:
    if not archived_projects:
        st.info("Nenhum projeto está arquivado.")
    else:
        archived_by_id = {item["id"]: item for item in archived_projects}
        selected_archived_id = st.selectbox(
            "Projeto arquivado",
            options=list(archived_by_id),
            format_func=lambda item_id: archived_by_id[item_id]["title"],
            key="lifecycle_archived_project",
        )
        selected_archived = archived_by_id[selected_archived_id]
        archived_preview = deletion_preview(selected_archived_id)
        _show_counts(archived_preview)
        st.caption(
            f"Arquivado em {selected_archived['archived_at']} · motivo: "
            f"{selected_archived.get('archived_reason') or 'não informado'}."
        )

        if st.button("↩️ Restaurar projeto", use_container_width=True):
            try:
                result = restore_project(
                    selected_archived_id,
                    actor=_actor_identifier(),
                )
            except Exception as error:
                st.error(f"Não foi possível restaurar o projeto: {error}")
            else:
                st.session_state["project_lifecycle_success"] = (
                    f"Projeto “{result['title']}” restaurado. Recibo: {result['event_id']}."
                )
                st.rerun()

        with st.expander("⚠️ Zona de exclusão permanente", expanded=False):
            st.error(
                "Esta operação remove definitivamente o projeto e seus dados relacionados "
                "do banco, além dos PDFs associados. Ela não pode ser desfeita pela interface."
            )
            if archived_preview["counts"]["active_jobs"]:
                st.warning("Há tarefas em andamento; a exclusão permanece bloqueada.")
            if archived_preview["backup_after_archive"]:
                backup = archived_preview["latest_backup"]
                st.success(
                    f"Backup posterior ao arquivamento encontrado: `{backup['filename']}` "
                    f"({backup['created_at']})."
                )
            else:
                st.warning(
                    "Crie e valide um backup completo **depois deste arquivamento**. "
                    "A exclusão continuará bloqueada até existir essa cópia de segurança."
                )
                st.page_link(
                    "views/9_Backup_Restauracao.py",
                    label="Abrir Backup e Restauração",
                    icon="🛡️",
                )

            with st.form(f"delete_project_{selected_archived_id}"):
                st.write(
                    "Para confirmar, digite exatamente o título: "
                    f"**{selected_archived['title']}**"
                )
                typed_title = st.text_input("Título do projeto")
                backup_ack = st.checkbox(
                    "Confirmei a integridade do backup indicado e guardei sua senha."
                )
                irreversible_ack = st.checkbox(
                    "Entendo que a exclusão permanente não pode ser desfeita sem restaurar o backup."
                )
                delete_submitted = st.form_submit_button(
                    "Excluir projeto permanentemente",
                    type="primary",
                    disabled=bool(
                        archived_preview["protected_reason"]
                        or archived_preview["counts"]["active_jobs"]
                        or not archived_preview["backup_after_archive"]
                    ),
                    use_container_width=True,
                )

            if delete_submitted:
                try:
                    if not irreversible_ack:
                        raise ValueError("Confirme que compreendeu o caráter permanente.")
                    result = permanently_delete_project(
                        selected_archived_id,
                        typed_title,
                        backup_confirmed=backup_ack,
                        actor=_actor_identifier(),
                    )
                except ValueError as error:
                    st.warning(str(error))
                except Exception as error:
                    st.error(f"Não foi possível excluir o projeto: {error}")
                else:
                    st.session_state["project_lifecycle_success"] = (
                        f"Projeto “{result['title']}” excluído permanentemente. "
                        f"Recibo preservado: {result['event_id']}."
                    )
                    if result.get("cleanup_warning"):
                        st.session_state["project_lifecycle_warning"] = result["cleanup_warning"]
                    st.rerun()

st.divider()
with st.expander("Histórico imutável do ciclo de vida", expanded=False):
    events = list_lifecycle_events()
    if not events:
        st.caption("Nenhum arquivamento, restauração ou exclusão foi registrado.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Data": item["created_at"],
                        "Ação": ACTION_LABELS.get(item["action"], item["action"]),
                        "Projeto": item["project_title"],
                        "Responsável": item["actor_identifier"],
                        "Recibo": item["id"],
                    }
                    for item in events
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
