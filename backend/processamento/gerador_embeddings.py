import psycopg2
from sentence_transformers import SentenceTransformer

# ==========================================
# 1. CARREGAR A INTELIGÊNCIA ARTIFICIAL
# ==========================================
print("🧠 A ligar os motores da IA...")
print("A descarregar/carregar o modelo 'all-MiniLM-L6-v2' (pode demorar 1 minuto na primeira vez)...")
modelo = SentenceTransformer('all-MiniLM-L6-v2')
print("✅ IA pronta a vetorizar!\n")

# ==========================================
# 2. FUNÇÃO DE CHUNKING (FATIAMENTO)
# ==========================================
def dividir_em_chunks(texto, tamanho_maximo=150):
    """
    Pega num texto longo e corta-o em blocos (chunks) de X palavras.
    Num projeto mais avançado, poderíamos usar bibliotecas como o LangChain para isto,
    mas para o nosso MVP, uma divisão por palavras é perfeita e ultra-rápida.
    """
    if not texto:
        return []
        
    palavras = texto.split()
    chunks = []
    
    # Percorre o texto e cria fatias de 150 em 150 palavras
    for i in range(0, len(palavras), tamanho_maximo):
        chunk = " ".join(palavras[i:i + tamanho_maximo])
        chunks.append(chunk)
        
    return chunks

# ==========================================
# 3. O MOTOR PRINCIPAL (Ler, Vetorizar e Gravar)
# ==========================================
def processar_artigos():
    # Ligar ao PostgreSQL local
    conexao = psycopg2.connect(
        host="localhost",
        port="5432",
        dbname="rag_systematic_review",
        user="rag_user",   
        password="rag_password"
    )
    cursor = conexao.cursor()

    # Vamos buscar todos os artigos que tenham um abstract preenchido
    print("🔍 A procurar artigos na base de dados...")
    cursor.execute("""
        SELECT id, abstract 
        FROM deduplicated_papers 
        WHERE abstract IS NOT NULL AND abstract != '';
    """)
    artigos = cursor.fetchall()
    
    print(f"📊 Encontrados {len(artigos)} artigos para processar. A iniciar validação de qualidade...\n")

    chunks_inseridos = 0
    artigos_ignorados = 0

    # Definição das mensagens de fallback que não contêm ciência real
    mensagens_lixo = [
        "Abstract indisponível.",
        "Abstract extraído do índice (simplificado para este exemplo).",
        "Abstract via PubMed E-Summary (Requer E-Fetch para texto completo)."
    ]

    for artigo_id, abstract in artigos:
        
        # --- FILTRO DE QUALIDADE SEMÂNTICA ---
        # 1. Verifica se o texto é uma das mensagens exatas de erro
        if abstract.strip() in mensagens_lixo:
            print(f"⚠️ Artigo ignorado (Mensagem de API): ID {artigo_id[:8]}...")
            artigos_ignorados += 1
            continue
            
        # 2. Verifica se o abstract é demasiado curto para conter contexto útil
        # (menos de 20 caracteres é provável que seja lixo ou um erro desconhecido)
        if len(abstract.strip()) < 20:
            print(f"⚠️ Artigo ignorado (Texto muito curto): ID {artigo_id[:8]}...")
            artigos_ignorados += 1
            continue
        # ---------------------------------------

        # A. Fatiar o resumo (Chunking)
        fatias = dividir_em_chunks(abstract, tamanho_maximo=150)

        for indice, pedaco_texto in enumerate(fatias):
            # B. Vetorizar (A Magia!)
            # O modelo lê o pedaço de texto e devolve uma lista de 384 números flutuantes
            vetor = modelo.encode(pedaco_texto).tolist()

            # C. Gravar no PostgreSQL usando a extensão pgvector
            cursor.execute(
                """
                INSERT INTO document_chunks (paper_id, chunk_index, chunk_text, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """,
                (artigo_id, indice, pedaco_texto, str(vetor))
            )
            chunks_inseridos += 1
            print(f"   -> Artigo {artigo_id[:8]}... | Chunk {indice} vetorizado e guardado.")

    # Confirmar as alterações na base de dados
    conexao.commit()
    cursor.close()
    conexao.close()

    print(f"\n🎉 Processo concluído com sucesso!")
    print(f"🧠 Total de {chunks_inseridos} 'fatias de conhecimento' reais vetorizadas.")
    print(f"🗑️ Total de {artigos_ignorados} artigos com abstracts inúteis descartados da vetorização.")

if __name__ == "__main__":
    processar_artigos()