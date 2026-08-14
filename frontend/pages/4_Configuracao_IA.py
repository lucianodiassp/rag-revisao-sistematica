import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.ai_admin_service import (  # noqa: E402
    get_ai_admin_state,
    import_environment_gemini_key,
    inspect_saved_gemini_key,
    save_ai_models,
    save_validated_gemini_key,
)
from backend.app.ai_config import (  # noqa: E402
    GENERATION_TASKS,
    TASK_EVALUATION,
    TASK_EXTRACTION,
    TASK_FORMULATION,
    TASK_RAG,
    TASK_RERANKING,
    TASK_REPORT,
    TASK_SCREENING,
)
from backend.app.ai_config_repository import (  # noqa: E402
    configuration_tables_available,
    list_configuration_audit,
)
from backend.app.secret_store import get_master_key_path  # noqa: E402


TASK_LABELS = {
    TASK_FORMULATION: "Formulação da pergunta",
    TASK_SCREENING: "Triagem",
    TASK_RAG: "Resposta RAG",
    TASK_RERANKING: "Reranking das evidências",
    TASK_EVALUATION: "Auditoria / juiz",
    TASK_EXTRACTION: "Extração de evidências",
    TASK_REPORT: "Relatório final",
}
STATUS_LABELS = {
    "valid": "✅ Válida",
    "invalid": "❌ Inválida",
    "untested": "⚪ Não testada",
}


st.set_page_config(page_title="Configuração de IA", page_icon="🔐", layout="wide")
st.title("🔐 Configuração de IA e Credenciais")
st.caption("Escopo atual: instalação local · usuário único")
st.info(
    "A chave é cifrada antes de chegar ao PostgreSQL. A chave-mestra permanece "
    "no perfil local do sistema operacional e nenhuma credencial é exibida ou registrada nos logs."
)

if not configuration_tables_available():
    st.error(
        "A migração de configuração de IA ainda não foi aplicada ao banco. "
        "Recrie o container e execute `004_ai_configuration.sql`."
    )
    st.stop()

try:
    estado = get_ai_admin_state()
except Exception as erro:
    st.error(f"Não foi possível carregar a configuração de IA: {erro}")
    st.stop()

credencial = estado["credential"]
if estado.get("configuration_error"):
    st.warning(
        "A configuração cifrada não pôde ser ativada. Cadastre novamente a chave "
        f"para recuperar a instalação. Detalhe: {estado['configuration_error']}"
    )

st.header("1. Provedor e credencial")
col_provider, col_status, col_source = st.columns(3)
col_provider.metric("Provedor", "Google Gemini")
col_status.metric(
    "Credencial",
    STATUS_LABELS.get(credencial["validation_status"], "Estado desconhecido")
    if credencial else "Não configurada",
)
col_source.metric(
    "Origem ativa",
    "Banco cifrado" if estado["credential_source"] == "encrypted_database" else "backend/.env",
)

if credencial:
    st.caption(
        f"{credencial['label']} · final {credencial['secret_hint']} · "
        f"último teste: {credencial['last_validated_at'] or 'não realizado'}"
    )
    if credencial.get("validation_error"):
        st.warning(f"Último erro registrado: {credencial['validation_error']}")

api_key = st.text_input(
    "Nova chave Gemini",
    type="password",
    placeholder="Cole a chave somente para testar e salvar",
    key="nova_chave_gemini",
)
rotulo_chave = st.text_input(
    "Identificação da chave",
    value=credencial["label"] if credencial else "Chave Gemini local",
)

col_salvar, col_importar, col_testar = st.columns(3)
with col_salvar:
    if st.button("Testar e salvar nova chave", type="primary", use_container_width=True):
        if not api_key.strip():
            st.error("Informe a nova chave antes de salvar.")
        else:
            with st.spinner("Validando a chave e consultando os modelos disponíveis..."):
                try:
                    _, catalogo = save_validated_gemini_key(api_key, rotulo_chave)
                    st.session_state["catalogo_modelos_ia"] = catalogo
                    st.session_state.pop("nova_chave_gemini", None)
                    st.success("Credencial validada, cifrada e salva.")
                    st.rerun()
                except Exception as erro:
                    st.error(f"A chave não foi salva: {erro}")

with col_importar:
    importar_desabilitado = not estado["environment_key_available"]
    if st.button(
        "Importar chave do backend/.env",
        use_container_width=True,
        disabled=importar_desabilitado,
    ):
        with st.spinner("Validando e importando a chave atual..."):
            try:
                _, catalogo = import_environment_gemini_key()
                st.session_state["catalogo_modelos_ia"] = catalogo
                st.success("Chave importada e armazenada de forma cifrada.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível importar a chave: {erro}")

with col_testar:
    if st.button(
        "Testar credencial salva",
        use_container_width=True,
        disabled=credencial is None,
    ):
        with st.spinner("Consultando os modelos liberados para esta chave..."):
            try:
                st.session_state["catalogo_modelos_ia"] = inspect_saved_gemini_key()
                st.success("Credencial válida.")
                st.rerun()
            except Exception as erro:
                st.error(f"Falha na validação: {erro}")

with st.expander("Onde fica a chave-mestra local?"):
    st.code(str(get_master_key_path()))
    st.caption(
        "Esse arquivo não pertence ao repositório. Para restaurar um backup do banco em "
        "outra máquina, será necessário cadastrar novamente a chave da API."
    )

st.divider()
st.header("2. Modelos por função")
catalogo = st.session_state.get("catalogo_modelos_ia")
if catalogo:
    st.success(
        f"Catálogo consultado: {len(catalogo['generative'])} modelo(s) generativo(s) e "
        f"{len(catalogo['embedding'])} modelo(s) de embedding."
    )
    with st.expander("Ver modelos disponíveis para esta chave"):
        col_gen, col_emb = st.columns(2)
        col_gen.write("**Generativos**")
        col_gen.code("\n".join(catalogo["generative"]) or "Nenhum identificado")
        col_emb.write("**Embeddings**")
        col_emb.code("\n".join(catalogo["embedding"]) or "Nenhum identificado")
else:
    st.caption(
        "Use um dos botões de teste acima para consultar os modelos disponíveis. "
        "Também é possível informar manualmente um identificador estável."
    )

with st.form("form_modelos_ia"):
    st.markdown("#### Modelos generativos")
    valores_modelos = {}
    for task in GENERATION_TASKS:
        config = estado["generation"][task]
        col_model, col_temp = st.columns([3, 1])
        modelo = col_model.text_input(
            TASK_LABELS[task],
            value=config.model,
            key=f"modelo_{task}",
        )
        temperatura_base = config.temperature if config.temperature is not None else 0.0
        temperatura = col_temp.number_input(
            f"Temperatura · {TASK_LABELS[task]}",
            min_value=0.0,
            max_value=2.0,
            value=float(temperatura_base),
            step=0.1,
            key=f"temperatura_{task}",
        )
        valores_modelos[task] = {
            "model_name": modelo,
            "temperature": temperatura,
        }

    st.markdown("#### Reranking da busca híbrida")
    config_reranking = estado["generation"][TASK_RERANKING]
    reranking_ativo = st.checkbox(
        "Reordenar os candidatos da busca híbrida antes de gerar a resposta",
        value=bool(config_reranking.enabled),
        help="Se ocorrer uma falha, o sistema usa automaticamente a ordem RRF original.",
    )
    col_candidatos, col_finais = st.columns(2)
    limite_candidatos = col_candidatos.number_input(
        "Candidatos recuperados pelo RRF",
        min_value=4,
        max_value=30,
        value=int(config_reranking.candidate_limit or 12),
        step=1,
    )
    limite_final = col_finais.number_input(
        "Trechos após o reranking",
        min_value=2,
        max_value=10,
        value=int(config_reranking.final_limit or 4),
        step=1,
    )
    valores_modelos[TASK_RERANKING].update(
        {
            "enabled": reranking_ativo,
            "candidate_limit": int(limite_candidatos),
            "final_limit": int(limite_final),
        }
    )

    st.markdown("#### Busca vetorial")
    col_embedding, col_dimensoes = st.columns([3, 1])
    modelo_embedding = col_embedding.text_input(
        "Modelo de embedding",
        value=estado["embedding"].model,
    )
    dimensoes = col_dimensoes.number_input(
        "Dimensões",
        min_value=768,
        max_value=768,
        value=int(estado["embedding"].dimensions),
        disabled=True,
        help="O schema pgvector atual utiliza exatamente 768 dimensões.",
    )
    embedding_alterado = modelo_embedding.strip() != estado["embedding"].model
    confirmar_reindexacao = st.checkbox(
        "Estou ciente de que a troca do modelo de embedding exige reindexar os PDFs "
        "e revisar novamente as extrações afetadas.",
        disabled=not embedding_alterado,
    )
    salvar_modelos = st.form_submit_button("💾 Salvar configuração de modelos", type="primary")

if salvar_modelos:
    if limite_final > limite_candidatos:
        st.error("O número de trechos finais não pode superar o total de candidatos.")
    elif embedding_alterado and not confirmar_reindexacao:
        st.error("Confirme a necessidade de reindexação antes de trocar o embedding.")
    else:
        try:
            save_ai_models(valores_modelos, modelo_embedding, dimensoes)
            st.success("Configuração salva. Os agentes já usarão os novos valores.")
            st.rerun()
        except Exception as erro:
            st.error(f"Não foi possível salvar a configuração: {erro}")

st.divider()
st.header("3. Configuração efetiva")
linhas = [
    {
        "Função": TASK_LABELS[task],
        "Modelo": config.model,
        "Temperatura efetiva": config.effective_temperature,
        "Ativo": config.enabled if task == TASK_RERANKING else None,
        "Candidatos": config.candidate_limit if task == TASK_RERANKING else None,
        "Trechos finais": config.final_limit if task == TASK_RERANKING else None,
        "Origem": config.source,
    }
    for task, config in estado["generation"].items()
]
linhas.append(
    {
        "Função": "Embedding",
        "Modelo": estado["embedding"].model,
        "Temperatura efetiva": None,
        "Ativo": None,
        "Candidatos": None,
        "Trechos finais": None,
        "Origem": estado["embedding"].source,
    }
)
st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True)

with st.expander("Histórico de alterações da configuração"):
    auditoria = list_configuration_audit(limit=20)
    if auditoria:
        st.dataframe(pd.DataFrame(auditoria), hide_index=True, use_container_width=True)
    else:
        st.caption("Nenhuma alteração registrada no banco até o momento.")
