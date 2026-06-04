from database import log_interacao_agente, salvar_artigo_coletado

print("--- Iniciando testes de inserção no banco ---")

# 1. Testando a função que a Pessoa 2 (Coleta) vai usar
salvar_artigo_coletado(
    id_artigo="11111111-2222-3333-4444-555555555555", # <-- UUID válido inventado para o teste
    titulo="O impacto do RAG na automação de revisões",
    abstract="Este é um artigo de teste inserido via script Python.",
    fontes_dict={"sources": ["OpenAlex", "TesteLocal"]}
)

# 2. Testando a função que a Pessoa 5 (Agentes) vai usar
log_interacao_agente(
    nome_agente="agente_teste_python",
    input_dict={"artigo_id": "11111111-2222-3333-4444-555555555555", "acao": "analisar_inclusao"},
    output_dict={"decisao": "include", "confianca": 0.99},
    modelo_dict={"provider": "ollama", "model": "llama3"}
)

print("\n--- Testes finalizados! Verifique as mensagens de sucesso acima. ---")