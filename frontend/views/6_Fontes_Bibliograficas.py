import os
import sys

import pandas as pd
import streamlit as st


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.bibliographic_admin_service import (  # noqa: E402
    get_bibliographic_admin_state,
    import_environment_source_key,
    inspect_effective_source_access,
    inspect_saved_source_key,
    remove_saved_source_key,
    save_source_settings,
    save_validated_source_key,
)
from backend.app.bibliographic_config import (  # noqa: E402
    SOURCE_LABELS,
    SOURCE_OPENALEX,
    SOURCE_PUBMED,
    SOURCE_SEMANTIC_SCHOLAR,
)
from backend.app.bibliographic_config_repository import (  # noqa: E402
    bibliographic_tables_available,
    list_configuration_audit,
)
from backend.app.secret_store import get_master_key_path  # noqa: E402
from backend.app.version import application_metadata  # noqa: E402


SOURCE_HELP = {
    SOURCE_OPENALEX: (
        "A chave e o e-mail são enviados como parâmetros oficiais da consulta. "
        "Sem chave, o acesso dependerá da política vigente do OpenAlex."
    ),
    SOURCE_SEMANTIC_SCHOLAR: (
        "A chave é enviada somente no cabeçalho x-api-key. A consulta sem chave "
        "continua disponível quando aceita pela API, com limites mais restritos."
    ),
    SOURCE_PUBMED: (
        "O PubMed aceita chave NCBI opcional. E-mail e identificação da aplicação "
        "acompanham as chamadas E-utilities."
    ),
}
STATUS_LABELS = {
    "valid": "✅ Válida",
    "invalid": "❌ Inválida",
    "untested": "⚪ Não testada",
}


st.set_page_config(page_title="Fontes bibliográficas", page_icon="🌐", layout="wide")
st.title("🌐 Fontes bibliográficas e credenciais")
metadata = application_metadata()
st.caption(
    f"Escopo atual: {metadata['deployment_label']} · {metadata['user_mode_label']}"
)
st.info(
    "As chaves são cifradas antes de chegar ao PostgreSQL. Os coletores recebem apenas "
    "a configuração efetiva em memória e nenhum segredo é salvo na proveniência das buscas."
)

if not bibliographic_tables_available():
    st.error(
        "A migração das fontes bibliográficas ainda não foi aplicada. "
        "Execute `database/scripts/005_bibliographic_sources.sql` no banco local."
    )
    st.stop()

try:
    estado = get_bibliographic_admin_state()
except Exception as erro:
    st.error(f"Não foi possível carregar a configuração das fontes: {erro}")
    st.stop()

if estado.get("configuration_error"):
    st.warning(
        "Uma credencial cifrada não pôde ser ativada. Cadastre-a novamente para esta "
        f"instalação. Detalhe: {estado['configuration_error']}"
    )

fontes = [SOURCE_OPENALEX, SOURCE_SEMANTIC_SCHOLAR, SOURCE_PUBMED]
abas = st.tabs([SOURCE_LABELS[codigo] for codigo in fontes])

for source_code, aba in zip(fontes, abas):
    with aba:
        item = estado["sources"][source_code]
        config = item["config"]
        credencial = item["credential"]

        st.write(SOURCE_HELP[source_code])
        col_ativa, col_acesso, col_origem = st.columns(3)
        col_ativa.metric("Fonte", "Ativa" if config.enabled else "Desativada")
        col_acesso.metric(
            "Credencial",
            STATUS_LABELS.get(credencial["validation_status"], "Estado desconhecido")
            if credencial else "Opcional / não salva",
        )
        col_origem.metric(
            "Origem da chave",
            "Banco cifrado"
            if config.credential_source == "encrypted_database"
            else ("Arquivo .env" if config.api_key else "Acesso sem chave"),
        )

        with st.form(f"configuracao_{source_code}"):
            habilitada = st.checkbox(
                "Consultar esta fonte durante a coleta",
                value=config.enabled,
            )
            col_email, col_tool = st.columns(2)
            email = col_email.text_input(
                "E-mail de contato",
                value=config.contact_email or "",
                help="Identificação recomendada pelas APIs para contato operacional.",
            )
            tool_name = col_tool.text_input(
                "Identificação da aplicação",
                value=config.tool_name,
            )
            col_timeout, col_retries = st.columns(2)
            timeout = col_timeout.number_input(
                "Timeout por chamada (segundos)",
                min_value=1,
                max_value=120,
                value=int(config.timeout_seconds),
            )
            tentativas = col_retries.number_input(
                "Máximo de tentativas",
                min_value=1,
                max_value=10,
                value=int(config.max_retries),
            )
            salvar_config = st.form_submit_button(
                "💾 Salvar configuração da fonte",
                type="primary",
            )

        if salvar_config:
            try:
                save_source_settings(
                    source_code,
                    habilitada,
                    email,
                    tool_name,
                    timeout,
                    tentativas,
                )
                st.success("Configuração salva e ativada no coletor.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível salvar a configuração: {erro}")

        st.markdown("#### Chave de API opcional")
        if credencial:
            st.caption(
                f"{credencial['label']} · final {credencial['secret_hint']} · "
                f"último teste: {credencial['last_validated_at'] or 'não realizado'}"
            )
            if credencial.get("validation_error"):
                st.warning(f"Último erro registrado: {credencial['validation_error']}")

        nova_chave = st.text_input(
            f"Nova chave {SOURCE_LABELS[source_code]}",
            type="password",
            placeholder="Cole a chave somente para testar e salvar",
            key=f"nova_chave_{source_code}",
        )
        rotulo = st.text_input(
            "Identificação da chave",
            value=(
                credencial["label"]
                if credencial else f"Chave {SOURCE_LABELS[source_code]} local"
            ),
            key=f"rotulo_chave_{source_code}",
        )

        col_salvar, col_importar, col_testar, col_remover = st.columns(4)
        with col_salvar:
            if st.button(
                "Testar e salvar nova chave",
                type="primary",
                use_container_width=True,
                key=f"salvar_chave_{source_code}",
            ):
                if not nova_chave.strip():
                    st.error("Informe a nova chave antes de salvar.")
                else:
                    with st.spinner("Validando acesso com uma consulta mínima..."):
                        try:
                            _, resultado = save_validated_source_key(
                                source_code,
                                nova_chave,
                                rotulo,
                            )
                            st.session_state[f"teste_fonte_{source_code}"] = resultado
                            st.success("Credencial validada, cifrada e salva.")
                            st.rerun()
                        except Exception as erro:
                            st.error(f"A chave não foi salva: {erro}")

        with col_importar:
            if st.button(
                "Importar chave do .env",
                use_container_width=True,
                disabled=not item["environment_key_available"],
                key=f"importar_chave_{source_code}",
            ):
                with st.spinner("Validando e importando a chave atual..."):
                    try:
                        _, resultado = import_environment_source_key(source_code)
                        st.session_state[f"teste_fonte_{source_code}"] = resultado
                        st.success("Chave importada e cifrada.")
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Não foi possível importar a chave: {erro}")

        with col_testar:
            if st.button(
                "Testar acesso ativo",
                use_container_width=True,
                key=f"testar_acesso_{source_code}",
            ):
                with st.spinner("Executando consulta mínima sem salvar artigos..."):
                    try:
                        resultado = (
                            inspect_saved_source_key(source_code)
                            if credencial else inspect_effective_source_access(source_code)
                        )
                        st.session_state[f"teste_fonte_{source_code}"] = resultado
                        st.success("A fonte respondeu corretamente.")
                        st.rerun()
                    except Exception as erro:
                        st.error(f"Falha na validação: {erro}")

        with col_remover:
            if st.button(
                "Remover chave salva",
                use_container_width=True,
                disabled=credencial is None,
                key=f"remover_chave_{source_code}",
            ):
                remove_saved_source_key(source_code)
                st.session_state.pop(f"teste_fonte_{source_code}", None)
                st.success("Credencial cifrada desativada.")
                st.rerun()

        ultimo_teste = st.session_state.get(f"teste_fonte_{source_code}")
        if ultimo_teste:
            modo = "com chave" if ultimo_teste["authenticated"] else "sem chave"
            st.success(
                f"Último teste: acesso {modo}, resposta HTTP {ultimo_teste['status_code']}."
            )

st.divider()
with st.expander("Segurança e chave-mestra local"):
    st.code(str(get_master_key_path()))
    st.caption(
        "A chave-mestra é compartilhada com a configuração de IA e não pertence ao "
        "repositório. Em outra máquina, recadastre as chaves ou restaure esse arquivo com segurança."
    )

with st.expander("Histórico de alterações das fontes"):
    auditoria = list_configuration_audit(limit=30)
    if auditoria:
        st.dataframe(pd.DataFrame(auditoria), hide_index=True, use_container_width=True)
    else:
        st.caption("Nenhuma alteração registrada no banco até o momento.")
