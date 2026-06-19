import streamlit as st
import sys
import os

# 1. Ajuste de Caminho (Para o Python encontrar a pasta 'backend')
# Adicionamos o diretório raiz ao caminho do sistema
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Agora podemos importar a nossa obra-prima da Pessoa 5!
from backend.agentes.agente_rag import responder_com_rag

# ==========================================
# 2. CONFIGURAÇÃO DA PÁGINA WEB
# ==========================================
st.set_page_config(
    page_title="RAG - Revisão Sistemática",
    page_icon="📚",
    layout="centered"
)

st.title("📚 Assistente de Revisão Sistemática")
st.markdown("""
Bem-vindo! Este assistente utiliza **Recuperação de Informação (pgvector)** e **Inteligência Artificial (Gemini)** para responder a perguntas com base nos artigos científicos recolhidos.
""")
st.divider()

# ==========================================
# 3. GESTÃO DO HISTÓRICO DE CONVERSA
# ==========================================
# O Streamlit recarrega o código a cada interação. O 'session_state' guarda a memória.
if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

# Desenhar as mensagens antigas no ecrã
for mensagem in st.session_state.mensagens:
    with st.chat_message(mensagem["role"]):
        st.markdown(mensagem["content"])

# ==========================================
# 4. INTERAÇÃO COM O UTILIZADOR
# ==========================================
# Caixa de texto no fundo do ecrã
pergunta_usuario = st.chat_input("Faça uma pergunta sobre a literatura aprovada (ex: Quais as arquiteturas utilizadas no SAD?)")

if pergunta_usuario:
    # A. Mostrar a pergunta do utilizador imediatamente e guardar no histórico
    with st.chat_message("user"):
        st.markdown(pergunta_usuario)
    st.session_state.mensagens.append({"role": "user", "content": pergunta_usuario})

    # B. Mostrar o "A pensar..." enquanto o nosso backend trabalha
    with st.chat_message("assistant"):
        with st.spinner("A pesquisar na base de dados e a ler artigos..."):
            try:
                # C. Chamar o nosso Agente (Pessoa 5) passando a pergunta
                resposta_agente = responder_com_rag(pergunta_usuario)
                
                # D. Imprimir a resposta no ecrã e guardar no histórico
                st.markdown(resposta_agente)
                st.session_state.mensagens.append({"role": "assistant", "content": resposta_agente})
                
            except Exception as e:
                st.error(f"⚠️ Ocorreu um erro de comunicação com o backend: {e}")