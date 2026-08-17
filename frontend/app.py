"""Ponto de entrada e navegação declarativa da interface Streamlit."""

import streamlit as st


st.set_page_config(
    page_title="RAG - Revisão Sistemática",
    page_icon="📚",
    # O roteador é executado antes de todas as páginas. Manter o layout global
    # como wide evita que a navegação interna reutilize temporariamente a largura
    # centralizada da página inicial até o próximo refresh do navegador.
    layout="wide",
)

pages = [
    st.Page(
        "assistente_revisao.py",
        title="Assistente de Revisão Sistemática",
        icon="📚",
        default=True,
    ),
    st.Page(
        "views/0_Configuracao_Pesquisa.py",
        title="Configuração da Pesquisa",
        icon="⚙️",
    ),
    st.Page("views/1_Triagem.py", title="Triagem", icon="🧑‍⚕️"),
    st.Page(
        "views/2_Matriz_Evidencias.py",
        title="Matriz de Evidências",
        icon="📊",
    ),
    st.Page(
        "views/3_Relatorio_Final.py",
        title="Relatório Final",
        icon="📑",
    ),
    st.Page(
        "views/10_Qualidade_Metodologica.py",
        title="Qualidade Metodológica",
        icon="🧭",
    ),
    st.Page(
        "views/4_Configuracao_IA.py",
        title="Configuração de IA",
        icon="🔐",
    ),
    st.Page("views/5_Gestao_PDFs.py", title="Gestão de PDFs", icon="📂"),
    st.Page(
        "views/6_Fontes_Bibliograficas.py",
        title="Fontes Bibliográficas",
        icon="🌐",
    ),
    st.Page("views/7_Deduplicacao.py", title="Deduplicação", icon="🔎"),
    st.Page(
        "views/8_Avaliacao_Quantitativa_RAG.py",
        title="Avaliação Quantitativa do RAG",
        icon="🧪",
    ),
    st.Page(
        "views/9_Backup_Restauracao.py",
        title="Backup e Restauração",
        icon="🛡️",
    ),
]

selected_page = st.navigation(pages)
selected_page.run()
