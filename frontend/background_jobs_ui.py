"""Componentes Streamlit compartilhados para processamentos persistentes."""

import streamlit as st

from backend.app.background_jobs import (
    ACTIVE_STATUSES,
    enqueue_job,
    get_latest_job,
    retry_job,
)


STATUS_LABELS = {
    "queued": "Na fila",
    "running": "Em execução",
    "retry_wait": "Aguardando nova tentativa automática",
    "succeeded": "Concluído",
    "failed": "Não concluído",
    "cancelled": "Cancelado",
}


def start_job(project_id, job_type, parameters=None):
    job, created = enqueue_job(project_id, job_type, parameters or {})
    if created:
        st.success(
            "Processamento colocado na fila. Você pode atualizar ou fechar esta página; "
            "o andamento permanecerá registrado."
        )
    else:
        st.info("Este processamento já está na fila ou em execução.")
    return job


def render_job_status(project_id, job_type, *, key, title="Andamento", parameters=None):
    """Mostra o último estado persistido e oferece atualização/repetição segura."""
    job = get_latest_job(project_id, job_type, parameters=parameters)
    if not job:
        return None

    status = job["status"]
    message = job.get("progress_message") or STATUS_LABELS.get(status, status)
    with st.container(border=True):
        col_title, col_refresh = st.columns([4, 1])
        col_title.markdown(f"**{title}: {STATUS_LABELS.get(status, status)}**")
        if status in ACTIVE_STATUSES:
            col_refresh.button(
                "Atualizar",
                key=f"refresh_job_{key}_{job['id']}",
                use_container_width=True,
            )

        current = int(job.get("progress_current") or 0)
        total = int(job.get("progress_total") or 0)
        if status in ACTIVE_STATUSES and total:
            st.progress(min(current / total, 1.0), text=message)
        else:
            st.caption(message)

        attempts = int(job.get("attempt_count") or 0)
        max_attempts = int(job.get("max_attempts") or 1)
        if status == "retry_wait":
            st.warning(
                f"Uma indisponibilidade temporária foi detectada. Tentativa "
                f"{attempts}/{max_attempts}; o sistema tentará novamente sem perder o registro."
            )
        elif status == "failed":
            st.error(job.get("error_message") or "O processamento não foi concluído.")
            if st.button(
                "Tentar novamente",
                key=f"retry_job_{key}_{job['id']}",
                type="primary",
            ):
                try:
                    retry_job(project_id, job["id"])
                    st.rerun()
                except Exception as error:
                    st.error(f"Não foi possível repetir o processamento: {error}")
        elif status == "succeeded":
            st.success("Processamento concluído e resultado registrado.")

        if job.get("created_at"):
            st.caption(
                f"Solicitado em {job['created_at']} · "
                f"tentativa(s): {attempts}/{max_attempts}"
            )
    return job


def job_is_active(job):
    return bool(job and job.get("status") in ACTIVE_STATUSES)
