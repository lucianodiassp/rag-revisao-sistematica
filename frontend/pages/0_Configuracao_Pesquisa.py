import os
import sys
import json
import streamlit as st

# Adiciona o caminho raiz para podermos importar os agentes do backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.agentes.agente_formulador import estruturar_pergunta_pesquisa
from backend.coleta.orquestrador_coleta import iniciar_recolha # <-- O NOVO IMPORT DA COLETA

st.set_page_config(page_title="Configuração da Pesquisa", page_icon="⚙️", layout="wide")

st.title("⚙️ Formulação da Pergunta de Pesquisa")
st.markdown("Defina o escopo da sua Revisão Sistemática. A Inteligência Artificial ajudará a enquadrar a sua pergunta na metodologia **PICO** e a gerar a estratégia de busca booleana.")
st.divider()

# Caminho para salvar o arquivo gerado
CAMINHO_JSON_PERGUNTA = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../research_question.json'))

# Formulário de Entrada
pergunta_livre = st.text_area(
    "Qual é a sua pergunta de pesquisa ou tema principal?",
    placeholder="Ex: Como o uso de modelos de linguagem grandes afeta a precisão no diagnóstico médico?",
    height=100
)

if st.button("🧠 Estruturar Pergunta (IA)", type="primary"):
    if not pergunta_livre.strip():
        st.warning("Por favor, digite uma pergunta ou tema de pesquisa.")
    else:
        with st.spinner("A processar metodologia PICO e a gerar strings de busca..."):
            resultado = estruturar_pergunta_pesquisa(pergunta_livre)
            
            if resultado:
                with open(CAMINHO_JSON_PERGUNTA, 'w', encoding='utf-8') as f:
                    json.dump(resultado, f, indent=4, ensure_ascii=False)
                
                st.success("Configuração gerada e salva com sucesso (`research_question.json`)!")
                
                st.subheader("1. Estrutura PICO")
                col1, col2, col3, col4 = st.columns(4)
                col1.info(f"**População (P):**\n{resultado['pico']['population']}")
                col2.success(f"**Intervenção (I):**\n{resultado['pico']['intervention']}")
                col3.warning(f"**Comparação (C):**\n{resultado['pico']['comparison']}")
                col4.error(f"**Desfecho (O):**\n{resultado['pico']['outcome']}")
                
                st.divider()
                st.subheader("2. Estratégia de Busca Recomendada")
                st.code(resultado['search_string'], language="sql")
                
                st.divider()
                st.subheader("3. Critérios de Elegibilidade")
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Critérios de Inclusão:**")
                    for inc in resultado['inclusion_criteria']:
                        st.write(f"- ✅ {inc}")
                with c2:
                    st.write("**Critérios de Exclusão:**")
                    for exc in resultado['exclusion_criteria']:
                        st.write(f"- ❌ {exc}")
            else:
                st.error("Ocorreu um erro ao gerar a estrutura. Tente novamente.")

st.divider()

# ==========================================
# SECÇÃO DE COLETA AUTOMATIZADA
# ==========================================
if os.path.exists(CAMINHO_JSON_PERGUNTA):
    st.write("### 📌 Configuração Atual Ativa e Coleta")
    with open(CAMINHO_JSON_PERGUNTA, 'r', encoding='utf-8') as f:
        dados_salvos = json.load(f)
        
    termo_busca = dados_salvos.get("search_string", "")
    
    # Divide a tela em duas colunas para ficar elegante
    col_json, col_coleta = st.columns([1, 1])
    
    with col_json:
        st.json(dados_salvos)
        
    with col_coleta:
        st.info("A sua estratégia de busca está pronta para ser executada nas bases de dados científicas (PubMed, OpenAlex, Semantic Scholar).")
        
        # --- NOVO BLOCO: CAMPO EDITÁVEL PARA A STRING DE BUSCA ---
        st.markdown("### 🔧 Ajuste Fino da Estratégia")
        string_manual = st.text_area(
            "String de Busca Booleana (Edite livremente antes de coletar):",
            value=termo_busca,
            height=150,
            help="Pode apagar o conteúdo gerado pela IA e colar a sua própria string de busca aqui."
        )
        
        # O utilizador pode escolher o tamanho da amostra
        qtd_artigos = st.slider("Máximo de artigos por fonte (API):", min_value=5, max_value=50, value=10, step=5)
        st.write(f"*Total estimado: Até {qtd_artigos * 3} artigos combinados.*")
        
        # O Botão que aciona o Orquestrador
        if st.button("🚀 Iniciar Coleta nas Bases de Dados", type="primary", use_container_width=True):
            if string_manual.strip(): # Passamos a usar a string_manual editada!
                with st.spinner(f"A contactar APIs científicas e a recolher até {qtd_artigos} artigos por base. Isto pode demorar um pouco..."):
                    try:
                        # Agora enviamos a string que está na caixa de texto, com os ajustes do utilizador
                        qtd_salvos, qtd_encontrados = iniciar_recolha(string_manual.strip(), max_por_fonte=qtd_artigos)
                        
                        if qtd_encontrados == 0:
                            st.warning("⚠️ A busca não encontrou nenhum artigo nas bases de dados. Tente ajustar a string acima para ser mais abrangente.")
                        elif qtd_salvos == 0:
                            st.info(f"ℹ️ Foram encontrados {qtd_encontrados} artigos nas APIs, mas **todos já existiam** na sua base de dados (Bloqueados pela regra de deduplicação).")
                        else:
                            st.success(f"✅ Coleta concluída com sucesso! Dos {qtd_encontrados} artigos encontrados, **{qtd_salvos} novos artigos** foram salvos na base de dados.")
                            st.balloons()
                            st.markdown("👉 **O próximo passo:** Vá à página **'Triagem'** no menu lateral para avaliar os novos artigos.")
                            
                    except Exception as e:
                        st.error(f"Ocorreu um erro durante a coleta: {e}")
            else:
                st.error("A string de busca não pode estar vazia. Por favor, preencha o campo acima.")