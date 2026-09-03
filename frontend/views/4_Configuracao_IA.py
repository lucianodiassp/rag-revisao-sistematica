import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.ai_admin_service import (  # noqa: E402
    get_ai_admin_state,
    import_environment_provider_key,
    inspect_saved_provider_key,
    save_ai_models,
    save_validated_provider_key,
)
from backend.app.ai_config import (  # noqa: E402
    GENERATION_TASKS,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_OPENAI,
    SUPPORTED_GENERATION_PROVIDERS,
    TASK_EVALUATION,
    TASK_EXTRACTION,
    TASK_FORMULATION,
    TASK_METHOD_QUALITY,
    TASK_RAG,
    TASK_RERANKING,
    TASK_REPORT,
    TASK_SCREENING,
    TASK_VISUAL_INTERPRETATION,
)
from backend.app.ai_config_repository import (  # noqa: E402
    configuration_tables_available,
    list_configuration_audit,
)
from backend.app.secret_store import get_master_key_path  # noqa: E402
from backend.app.version import application_metadata  # noqa: E402


TASK_LABELS = {
    TASK_FORMULATION: "Formulação da pergunta",
    TASK_SCREENING: "Triagem",
    TASK_RAG: "Resposta RAG",
    TASK_RERANKING: "Reranking das evidências",
    TASK_EVALUATION: "Auditoria / juiz",
    TASK_EXTRACTION: "Extração de evidências",
    TASK_METHOD_QUALITY: "Qualidade metodológica",
    TASK_REPORT: "Relatório final",
    TASK_VISUAL_INTERPRETATION: "Interpretação visual",
}
STATUS_LABELS = {
    "valid": "✅ Válida",
    "invalid": "❌ Inválida",
    "untested": "⚪ Não testada",
}
PROVIDER_LABELS = {
    PROVIDER_GOOGLE_GEMINI: "Google Gemini",
    PROVIDER_OPENAI: "OpenAI",
}


st.set_page_config(page_title="Configuração de IA", page_icon="🔐", layout="wide")
st.title("🔐 Configuração de IA e Credenciais")
metadata = application_metadata()
st.caption(
    f"Escopo atual: {metadata['deployment_label']} · {metadata['user_mode_label']}"
)
st.info(
    "A chave é cifrada antes de chegar ao PostgreSQL. A chave-mestra permanece "
    "no armazenamento privado da instalação e nenhuma credencial é exibida ou registrada nos logs."
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

if estado.get("configuration_error"):
    st.warning(
        "A configuração cifrada não pôde ser ativada. Cadastre novamente a chave "
        f"para recuperar a instalação. Detalhe: {estado['configuration_error']}"
    )

st.header("1. Provedor e credencial")
provider_selected = st.selectbox(
    "Provedor para configurar",
    options=SUPPORTED_GENERATION_PROVIDERS,
    format_func=lambda item: PROVIDER_LABELS[item],
)
credencial = estado["credentials"].get(provider_selected)
environment_available = estado["environment_keys_available"].get(provider_selected, False)
col_provider, col_status, col_source = st.columns(3)
col_provider.metric("Provedor", PROVIDER_LABELS[provider_selected])
col_status.metric(
    "Credencial",
    STATUS_LABELS.get(credencial["validation_status"], "Estado desconhecido")
    if credencial else "Não configurada",
)
col_source.metric(
    "Origem ativa",
    "Banco cifrado"
    if credencial
    else "Ambiente"
    if environment_available
    else "Não configurada",
)

if credencial:
    st.caption(
        f"{credencial['label']} · final {credencial['secret_hint']} · "
        f"último teste: {credencial['last_validated_at'] or 'não realizado'}"
    )
    if credencial.get("validation_error"):
        st.warning(f"Último erro registrado: {credencial['validation_error']}")

api_key = st.text_input(
    f"Nova chave {PROVIDER_LABELS[provider_selected]}",
    type="password",
    placeholder="Cole a chave somente para testar e salvar",
    key=f"nova_chave_{provider_selected}",
)
rotulo_chave = st.text_input(
    "Identificação da chave",
    value=(
        credencial["label"]
        if credencial
        else f"Chave {PROVIDER_LABELS[provider_selected]} local"
    ),
    key=f"rotulo_chave_{provider_selected}",
)

col_salvar, col_importar, col_testar = st.columns(3)
with col_salvar:
    if st.button("Testar e salvar nova chave", type="primary", use_container_width=True):
        if not api_key.strip():
            st.error("Informe a nova chave antes de salvar.")
        else:
            with st.spinner("Validando a chave e consultando os modelos disponíveis..."):
                try:
                    _, catalogo = save_validated_provider_key(
                        provider_selected, api_key, rotulo_chave
                    )
                    st.session_state.setdefault("catalogos_modelos_ia", {})[
                        provider_selected
                    ] = catalogo
                    st.session_state.pop(f"nova_chave_{provider_selected}", None)
                    st.success("Credencial validada, cifrada e salva.")
                    st.rerun()
                except Exception as erro:
                    st.error(f"A chave não foi salva: {erro}")

with col_importar:
    importar_desabilitado = not environment_available
    if st.button(
        "Importar chave do ambiente",
        use_container_width=True,
        disabled=importar_desabilitado,
    ):
        with st.spinner("Validando e importando a chave atual..."):
            try:
                _, catalogo = import_environment_provider_key(provider_selected)
                st.session_state.setdefault("catalogos_modelos_ia", {})[
                    provider_selected
                ] = catalogo
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
                st.session_state.setdefault("catalogos_modelos_ia", {})[
                    provider_selected
                ] = inspect_saved_provider_key(provider_selected)
                st.success("Credencial válida.")
                st.rerun()
            except Exception as erro:
                st.error(f"Falha na validação: {erro}")

with st.expander("Onde fica a chave-mestra local?"):
    st.code(str(get_master_key_path()))
    st.caption(
        "Esse arquivo não pertence ao repositório. O backup completo criado pela página "
        "Backup e Restauração pode incluí-lo dentro do arquivo protegido por senha."
    )

st.divider()
st.header("2. Modelos por função")
catalogo = st.session_state.get("catalogos_modelos_ia", {}).get(provider_selected)
if catalogo:
    st.success(
        f"Catálogo {PROVIDER_LABELS[provider_selected]}: "
        f"{len(catalogo['generative'])} modelo(s) generativo(s) e "
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
        col_provider_task, col_model, col_temp = st.columns([1.4, 3, 1])
        provider_task = col_provider_task.selectbox(
            f"Provedor · {TASK_LABELS[task]}",
            options=SUPPORTED_GENERATION_PROVIDERS,
            index=SUPPORTED_GENERATION_PROVIDERS.index(config.provider),
            format_func=lambda item: PROVIDER_LABELS[item],
            key=f"provider_{task}",
        )
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
            "provider_code": provider_task,
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
    peso_rrf = st.slider(
        "Peso da ordem original da busca híbrida (RRF)",
        min_value=0.0,
        max_value=1.0,
        value=float(config_reranking.rrf_weight or 0.0),
        step=0.05,
        help=(
            "0 mantém somente a ordem proposta pela IA; 1 mantém somente a ordem "
            "RRF. Valores intermediários combinam os dois sinais. Use o benchmark "
            "para escolher o peso."
        ),
    )
    valores_modelos[TASK_RERANKING].update(
        {
            "enabled": reranking_ativo,
            "candidate_limit": int(limite_candidatos),
            "final_limit": int(limite_final),
            "rrf_weight": float(peso_rrf),
        }
    )

    st.markdown("#### Busca vetorial")
    st.caption(
        "Nesta entrega, os embeddings permanecem no Google Gemini para preservar "
        "os vetores de 768 dimensões já indexados."
    )
    col_embedding_provider, col_embedding, col_dimensoes = st.columns([1.4, 3, 1])
    col_embedding_provider.text_input(
        "Provedor de embedding",
        value=PROVIDER_LABELS[PROVIDER_GOOGLE_GEMINI],
        disabled=True,
    )
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
    providers_used = {
        item["provider_code"] for item in valores_modelos.values()
    } | {PROVIDER_GOOGLE_GEMINI}
    missing_credentials = sorted(
        provider
        for provider in providers_used
        if provider not in estado["credentials"]
        and not estado["environment_keys_available"].get(provider, False)
    )
    if missing_credentials:
        st.error(
            "Cadastre e valide primeiro as credenciais de: "
            + ", ".join(PROVIDER_LABELS[item] for item in missing_credentials)
            + "."
        )
    elif limite_final > limite_candidatos:
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
        "Provedor": PROVIDER_LABELS.get(config.provider, config.provider),
        "Modelo": config.model,
        "Temperatura efetiva": config.effective_temperature,
        "Ativo": config.enabled if task == TASK_RERANKING else None,
        "Candidatos": config.candidate_limit if task == TASK_RERANKING else None,
        "Trechos finais": config.final_limit if task == TASK_RERANKING else None,
        "Peso RRF": config.rrf_weight if task == TASK_RERANKING else None,
        "Origem": config.source,
    }
    for task, config in estado["generation"].items()
]
linhas.append(
    {
        "Função": "Embedding",
        "Provedor": PROVIDER_LABELS.get(
            estado["embedding"].provider, estado["embedding"].provider
        ),
        "Modelo": estado["embedding"].model,
        "Temperatura efetiva": None,
        "Ativo": None,
        "Candidatos": None,
        "Trechos finais": None,
        "Peso RRF": None,
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
