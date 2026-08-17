# Agentic System Blueprint

## 1. Visao do sistema agentico

O sistema proposto e um MVP para apoiar revisoes sistematicas usando RAG e agentes de IA.

A solucao combina:

- PostgreSQL como banco principal.
- pgvector para busca vetorial.
- FastAPI para expor a API do backend.
- CrewAI como camada de orquestracao dos agentes.
- OpenAI ou Ollama para LLM e embeddings.
- Registro de interacoes para rastreabilidade das decisoes.

O foco do MVP e demonstrar um fluxo funcional ponta a ponta: criar um projeto de revisao, carregar artigos de exemplo, recuperar contexto com RAG, acionar agentes especializados e registrar decisoes justificadas.

Premissa metodologica:

O sistema nao automatiza uma revisao sistematica completa. Ele apoia, registra e audita decisoes humanas em etapas criticas da revisao: protocolo, estrategia de busca, importacao, deduplicacao, triagem, extracao de evidencias, avaliacao preliminar da qualidade e sintese narrativa.

Assim, a IA sugere, organiza, justifica, aponta inconsistencias e mantem rastreabilidade. A decisao final permanece humana.

## 2. Problema atendido

Revisoes sistematicas exigem leitura, triagem, extracao e sintese de muitos estudos. Esse processo e trabalhoso, repetitivo e sujeito a inconsistencias entre revisores.

O sistema busca reduzir o esforco operacional dos pesquisadores, mantendo rastreabilidade e participacao humana nas decisoes criticas.

## 3. Objetivo do sistema

Criar um MVP multiagente com RAG para apoiar revisoes sistematicas.

Objetivos especificos:

- Organizar projetos de revisao sistematica.
- Armazenar artigos, resumos e metadados.
- Gerar embeddings dos textos relevantes.
- Recuperar contexto por similaridade semantica.
- Acionar agentes para triagem, extracao e sintese.
- Registrar entradas, saidas, justificativas e modelo usado.
- Permitir curadoria humana das decisoes.

## 4. Usuarios e papeis humanos

### 4.1 Pesquisador principal

Define a pergunta de pesquisa, os criterios de inclusao/exclusao e valida o desenho geral da revisao.

### 4.2 Revisor humano

Valida ou corrige decisoes sugeridas pelos agentes, principalmente triagem e extracao de evidencias.

### 4.3 Orientador ou professor

Avalia o fluxo, a coerencia metodologica e a rastreabilidade das decisoes.

### 4.4 Administrador tecnico

Configura ambiente, banco, chaves de API, modelos e execucao local.

## 5. Agentes participantes

### 5.1 Agent Card - Agente de Protocolo

**Nome:** ProtocolAgent

**Objetivo:** Apoiar a estruturacao inicial da revisao sistematica.

**Responsabilidades:**

- Analisar a pergunta de pesquisa.
- Sugerir refinamentos para objetivo, escopo e criterios.
- Apoiar a definicao de criterios de inclusao e exclusao.

**Entradas:**

- Tema da revisao.
- Pergunta de pesquisa.
- Objetivos informados pelo pesquisador.
- Criterios preliminares.

**Saidas:**

- Pergunta refinada.
- Objetivo da revisao.
- Criterios de inclusao e exclusao sugeridos.
- Justificativa das sugestoes.

**Ferramentas:**

- LLM.
- Banco de dados.
- Logger de interacoes.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `review_projects`
- `agent_interactions`

### 5.2 Agent Card - Agente de Estrategia de Busca

**Nome:** SearchStrategyAgent

**Objetivo:** Sugerir strings e estrategias de busca para bases cientificas.

**Responsabilidades:**

- Gerar termos relacionados a pergunta de pesquisa.
- Propor strings booleanas.
- Separar termos por base ou fonte, quando aplicavel.

**Entradas:**

- Pergunta de pesquisa.
- Criterios de inclusao/exclusao.
- Palavras-chave.
- Bases-alvo, se informadas.

**Saidas:**

- Strings de busca.
- Justificativa dos termos usados.
- Fontes recomendadas.

**Ferramentas:**

- LLM.
- Banco de dados.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `search_queries`
- `agent_interactions`

### 5.3 Agent Card - Agente de Importacao e Deduplicacao

**Nome:** ImportDedupAgent

**Objetivo:** Apoiar a importacao de metadados e a identificacao de registros duplicados.

**Responsabilidades:**

- Validar campos minimos dos registros importados.
- Identificar duplicados por DOI, titulo, autores, ano e fonte.
- Sugerir consolidacao de registros equivalentes.
- Preservar a origem de cada registro recuperado.

**Entradas:**

- Registros brutos importados.
- Fonte de origem.
- String de busca usada.
- Data da busca.
- Filtros aplicados.

**Saidas:**

- Registros normalizados.
- Grupos de duplicados sugeridos.
- Registro canonico sugerido.
- Justificativa da deduplicacao.

**Ferramentas:**

- Banco de dados.
- Regras deterministicas.
- LLM, quando houver ambiguidade textual.

**Curadoria humana obrigatoria:** sim para consolidacoes ambiguas.

**Tabelas relacionadas:**

- `search_queries`
- `retrieved_records`
- `deduplicated_papers`
- `agent_interactions`

### 5.4 Agent Card - Agente de Triagem

**Nome:** ScreeningAgent

**Objetivo:** Sugerir inclusao, exclusao ou incerteza para artigos com base na fase de selecao, no texto disponivel e nos criterios aprovados.

**Responsabilidades:**

- Avaliar titulo e resumo na fase F1.
- Apoiar analise de introducao, conclusao ou texto completo nas fases F2/F3.
- Comparar o artigo com criterios de inclusao/exclusao.
- Gerar decisao sugerida.
- Explicar a decisao com base no texto disponivel.

**Entradas:**

- Titulo.
- Resumo.
- Metadados do artigo.
- Criterios de inclusao/exclusao.
- Contexto recuperado via RAG, quando aplicavel; na F1, apenas para apoio a interpretacao dos criterios, nunca para inferir conteudo ausente no artigo.

**Saidas:**

- `include`, `exclude` ou `uncertain`.
- Fase de selecao: `F1`, `F2` ou `F3`.
- Criterios aplicados, como `I01`, `I02`, `E01`.
- Fonte da evidencia: titulo, resumo, introducao, conclusao ou texto completo.
- Nivel de confianca.
- Justificativa.
- Evidencias textuais usadas.

**Ferramentas:**

- Retriever RAG com pgvector.
- LLM.
- Banco de dados.
- Logger de interacoes.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `deduplicated_papers`
- `paper_chunks`
- `embeddings_metadata`
- `screening_decisions`
- `agent_interactions`

### 5.5 Agent Card - Agente de Elegibilidade

**Nome:** EligibilityAgent

**Objetivo:** Apoiar a avaliacao de elegibilidade em fases posteriores a triagem inicial.

**Responsabilidades:**

- Avaliar criterios em F2/F3 com textos mais completos.
- Sinalizar informacao insuficiente.
- Comparar decisao preliminar com evidencia textual mais detalhada.
- Recomendar revisao humana em casos ambiguos.

**Entradas:**

- Decisao de F1.
- Introducao, conclusao ou texto completo.
- Criterios de inclusao/exclusao.
- Historico de decisoes.

**Saidas:**

- Decisao sugerida de elegibilidade.
- Criterios aplicados.
- Evidencias textuais.
- Motivo de exclusao, quando aplicavel.

**Ferramentas:**

- Retriever RAG.
- LLM.
- Banco de dados.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `deduplicated_papers`
- `screening_decisions`
- `agent_interactions`

### 5.6 Agent Card - Agente de Extracao de Evidencias

**Nome:** EvidenceExtractionAgent

**Objetivo:** Extrair informacoes estruturadas dos artigos selecionados.

**Responsabilidades:**

- Identificar populacao, contexto, metodo, intervencao/fenomeno e resultados.
- Extrair trechos relevantes.
- Produzir uma matriz de evidencias preliminar.

**Entradas:**

- Texto do artigo ou resumo.
- Chunks recuperados via RAG.
- Pergunta de pesquisa.
- Campos de extracao esperados.

**Saidas:**

- Dados extraidos em JSON.
- Evidencias textuais.
- Campos ausentes ou incertos.
- Justificativa.

**Ferramentas:**

- Retriever RAG.
- LLM.
- Banco de dados.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `extracted_evidence`
- `agent_interactions`

### 5.7 Agent Card - Agente de Avaliacao de Qualidade

**Nome:** QualityAssessmentAgent

**Objetivo:** Apoiar a avaliacao preliminar da qualidade metodologica dos estudos com base em checklists definidos previamente.

**Responsabilidades:**

- Avaliar sinais de qualidade metodologica.
- Identificar limitacoes do estudo.
- Sinalizar risco de vies quando houver informacao suficiente.
- Aplicar checklist compativel com o tipo de estudo.

**Entradas:**

- Metadados do artigo.
- Resumo ou texto completo.
- Evidencias extraidas.
- Checklist metodologico definido pelo pesquisador.

**Saidas:**

- Avaliacao preliminar.
- Checklist aplicado.
- Pontos fortes.
- Limitacoes.
- Incertezas.

**Ferramentas:**

- LLM.
- Retriever RAG.
- Banco de dados.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `methodological_assessment_instruments`
- `methodological_assessments`
- `methodological_assessment_sources`
- `agent_interactions`

**Observacao metodologica:** qualidade metodologica nao deve excluir automaticamente um estudo, salvo quando isso estiver definido no protocolo. Ela deve ponderar a forca da evidencia na sintese.

### 5.8 Agent Card - Agente de Resolucao de Conflitos

**Nome:** ConflictResolutionAgent

**Objetivo:** Identificar divergencias entre decisoes de agentes e revisores humanos.

**Responsabilidades:**

- Comparar decisoes de revisores.
- Comparar decisao humana e decisao sugerida pelo agente.
- Sinalizar conflitos de criterio.
- Gerar relatorio de pendencias para curadoria.

**Entradas:**

- Decisoes de triagem.
- Criterios aplicados.
- Justificativas.
- Historico de revisoes humanas.

**Saidas:**

- Lista de conflitos.
- Tipo de conflito.
- Recomendacao de revisao.
- Evidencias associadas.

**Ferramentas:**

- Banco de dados.
- Regras deterministicas.
- LLM para resumir conflitos.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `screening_decisions`
- `agent_interactions`

### 5.9 Agent Card - Agente de Integridade de Referencias

**Nome:** ReferenceIntegrityAgent

**Objetivo:** Verificar consistencia bibliografica e metadados dos estudos.

**Responsabilidades:**

- Verificar DOI, titulo, autores, ano e fonte.
- Sinalizar metadados incompletos.
- Apoiar padronizacao de referencias.
- Identificar inconsistencias entre citacao e referencia.

**Entradas:**

- Metadados dos registros.
- DOI.
- Fonte.
- Referencias exportadas.

**Saidas:**

- Alertas de inconsistencias.
- Campos ausentes.
- Sugestoes de correcao.
- Status de integridade da referencia.

**Ferramentas:**

- Banco de dados.
- Regras deterministicas.
- APIs externas no futuro, se necessario.

**Curadoria humana obrigatoria:** sim para correcao final.

**Tabelas relacionadas:**

- `retrieved_records`
- `deduplicated_papers`
- `agent_interactions`

### 5.10 Agent Card - Agente de Sintese

**Nome:** SynthesisAgent

**Objetivo:** Gerar uma sintese narrativa preliminar com base nas evidencias extraidas.

**Responsabilidades:**

- Agrupar achados semelhantes.
- Destacar convergencias e divergencias.
- Produzir uma sintese preliminar.
- Indicar lacunas de evidencia.

**Entradas:**

- Evidencias extraidas.
- Decisoes de triagem.
- Pergunta de pesquisa.
- Contexto recuperado via RAG.

**Saidas:**

- Sintese narrativa.
- Temas principais.
- Lacunas.
- Referencias aos estudos usados.

**Ferramentas:**

- LLM.
- Banco de dados.
- Retriever RAG.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `extracted_evidence`
- `deduplicated_papers`
- `agent_interactions`

### 5.11 Agent Card - Agente de Relatorio

**Nome:** ReportingAgent

**Objetivo:** Gerar artefatos de transparencia e apoio ao relatorio final da revisao.

**Responsabilidades:**

- Gerar tabela de exclusoes.
- Gerar resumo de busca por fonte.
- Consolidar numeros por fase.
- Apoiar insumos para fluxograma PRISMA.
- Produzir quadros e tabelas preliminares.

**Entradas:**

- Buscas executadas.
- Registros importados.
- Duplicados removidos.
- Decisoes por fase.
- Evidencias extraidas.

**Saidas:**

- Tabela de exclusoes.
- Resumo de selecao.
- Indicadores de rastreabilidade.
- Insumos para relatorio final.

**Ferramentas:**

- Banco de dados.
- Regras deterministicas.
- LLM para narrativa.

**Curadoria humana obrigatoria:** sim.

**Tabelas relacionadas:**

- `search_queries`
- `retrieved_records`
- `deduplicated_papers`
- `screening_decisions`
- `extracted_evidence`
- `agent_interactions`

### 5.12 Agent Card - Agente de Auditoria e Rastreabilidade

**Nome:** AuditAgent

**Objetivo:** Verificar se as decisoes dos agentes possuem justificativa, evidencia e registro adequado.

**Responsabilidades:**

- Conferir se uma decisao possui entrada, saida e justificativa.
- Sinalizar decisoes sem evidencias suficientes.
- Identificar respostas que extrapolam o contexto recuperado.

**Entradas:**

- Logs em `agent_interactions`.
- Decisoes de triagem.
- Evidencias extraidas.
- Contexto RAG usado.

**Saidas:**

- Alertas de auditoria.
- Pendencias de revisao humana.
- Indicadores de rastreabilidade.

**Ferramentas:**

- Banco de dados.
- Regras deterministicas.
- LLM, quando necessario.

**Curadoria humana obrigatoria:** nao para checagens simples; sim para conflitos metodologicos.

**Tabelas relacionadas:**

- `agent_interactions`
- `screening_decisions`
- `extracted_evidence`

## 6. Fluxo de orquestracao entre agentes

Fluxo MVP proposto:

1. Pesquisador cria um projeto de revisao.
2. ProtocolAgent ajuda a estruturar pergunta e criterios.
3. Usuario aprova ou ajusta os criterios.
4. SearchStrategyAgent sugere strings de busca por base.
5. Usuario valida strings, fontes, filtros e data da busca.
6. Sistema carrega artigos de exemplo ou registros exportados.
7. ImportDedupAgent normaliza registros e sugere duplicados.
8. Backend gera chunks e embeddings.
9. ScreeningAgent executa F1 com titulo, resumo e metadados.
10. Usuario valida decisoes de F1.
11. EligibilityAgent apoia F2/F3 quando houver texto mais completo.
12. EvidenceExtractionAgent extrai evidencias dos artigos incluidos.
13. QualityAssessmentAgent aplica checklist definido previamente.
14. SynthesisAgent gera uma sintese preliminar.
15. ConflictResolutionAgent sinaliza divergencias.
16. ReportingAgent gera insumos de transparencia.
17. AuditAgent verifica rastreabilidade e pendencias.
18. Professor visualiza o fluxo, decisoes e registros.

Fases de selecao:

- F1: triagem por titulo, resumo, palavras-chave e metadados.
- F2: avaliacao com trechos adicionais, como introducao e conclusao.
- F3: avaliacao com texto completo, quando disponivel.

Na F1, o agente deve decidir apenas com base nos metadados do proprio estudo e nos criterios aprovados. Contexto RAG externo pode ser usado para esclarecer criterios, mas nao para inferir conteudo ausente no artigo.

## 7. Entradas esperadas

- Titulo do projeto.
- Pergunta de pesquisa.
- Objetivo da revisao.
- Criterios de inclusao.
- Criterios de exclusao.
- Lista de artigos de exemplo.
- Titulo, resumo, DOI, fonte e metadados.
- String de busca usada por fonte.
- Data da busca.
- Filtros aplicados.
- Quantidade de resultados por fonte.
- Fase de selecao em execucao: F1, F2 ou F3.
- Chave de API ou configuracao de modelo local.

## 8. Saidas esperadas

- Projeto criado.
- Artigos armazenados.
- Chunks e embeddings gerados.
- Decisoes sugeridas de triagem.
- Criterios aplicados por decisao.
- Motivos de exclusao.
- Evidencias extraidas.
- Sintese preliminar.
- Logs de agentes.
- Itens pendentes de curadoria humana.
- Insumos de relatorio e transparencia.

## 9. Regras de decisao

Regras gerais:

- Nenhum agente deve tomar decisao final sem possibilidade de revisao humana.
- Toda decisao deve ter justificativa.
- Toda decisao de inclusao/exclusao deve registrar criterio aplicado.
- Toda decisao deve registrar a fase de selecao: F1, F2 ou F3.
- Toda justificativa deve se apoiar no titulo, resumo, texto ou contexto recuperado.
- Quando a evidencia for insuficiente, o agente deve retornar `uncertain`.
- Se houver conflito entre criterios, o caso deve ser encaminhado para curadoria humana.
- O agente nao deve inventar dados ausentes no artigo.

Regras para triagem:

- `include`: atende claramente aos criterios de inclusao e nao viola criterios de exclusao.
- `exclude`: viola criterio de exclusao ou nao atende criterios essenciais.
- `uncertain`: informacao insuficiente, ambigua ou contraditoria.

Formato esperado de uma decisao de triagem:

```json
{
  "decision": "include | exclude | uncertain",
  "criteria_applied": ["I01", "E03"],
  "screening_phase": "F1 | F2 | F3",
  "evidence_quote": "...",
  "evidence_source": "title | abstract | introduction | conclusion | full_text",
  "confidence": 0.82,
  "rationale": "...",
  "requires_human_review": true
}
```

Regra especifica para falso exclude:

Excluir indevidamente um estudo relevante e mais critico do que incluir temporariamente um estudo fraco. Decisoes de exclusao com baixa confianca devem ser revisadas por humano.

## 10. Memoria, contexto e historico

Memoria persistente:

- PostgreSQL para projetos, artigos, decisoes e evidencias.
- pgvector para embeddings e busca semantica.
- `agent_interactions` para logs de agentes.
- `screening_decisions` para decisoes de triagem.
- `extracted_evidence` para matriz de evidencias.

Contexto usado pelos agentes:

- Pergunta de pesquisa.
- Criterios aprovados.
- Historico de decisoes humanas.
- Chunks recuperados via RAG.
- Metadados dos artigos.

Artefatos metodologicos a manter:

- Protocolo versionado.
- Estrategia de busca por base.
- Registro de busca com data, filtros e quantidade de resultados.
- Registro de importacao.
- Registro de deduplicacao.
- Fases de selecao F1/F2/F3.
- Motivo de exclusao por estudo.
- Formulario de extracao.
- Checklist de qualidade.
- Sintese rastreavel.
- Relatorio de transparencia.

## 11. Ferramentas e integracoes

Ja disponivel no projeto:

- Docker Compose.
- PostgreSQL.
- pgvector.
- pgAdmin.
- Schema SQL inicial.
- Script Python simples de teste de conexao.

Complementos propostos para o MVP:

- FastAPI: API do sistema.
- Uvicorn: servidor local da API.
- CrewAI: orquestracao dos agentes.
- python-dotenv: leitura de `.env`.
- pydantic-settings: configuracao estruturada.
- psycopg2-binary: conexao Python com PostgreSQL.
- OpenAI ou Ollama: LLM e embeddings.
- pytest: testes basicos.

## 12. Pontos de curadoria humana

Curadoria obrigatoria:

- Validacao da pergunta de pesquisa.
- Validacao dos criterios de inclusao/exclusao.
- Validacao das strings de busca.
- Validacao de duplicados ambiguos.
- Revisao de decisoes `include`, `exclude` e `uncertain`.
- Revisao de exclusoes com baixa confianca.
- Revisao de evidencias extraidas.
- Revisao de avaliacao de qualidade.
- Aprovacao da sintese preliminar.

Curadoria recomendada:

- Casos com baixa confianca.
- Artigos sem resumo.
- Artigos com metadados incompletos.
- Decisoes divergentes entre agentes.

## 13. Guardrails, riscos e limites

Guardrails:

- O agente deve responder apenas com base no contexto disponivel.
- O agente deve indicar incerteza quando faltar informacao.
- O agente deve registrar justificativa.
- O agente deve registrar criterio aplicado e fase da selecao.
- O sistema deve salvar input, output, modelo e parametros.
- Decisoes finais devem permanecer sob responsabilidade humana.
- Na F1, RAG externo nao deve ser usado para inferir conteudo ausente no titulo, resumo ou metadados do estudo.

Riscos:

- Alucinacao do LLM.
- Criterios mal definidos.
- Embeddings inadequados ao dominio.
- Baixa qualidade dos resumos.
- Vies do modelo.
- Excesso de confianca em decisoes automaticas.

Limites do MVP:

- Nao realiza busca automatica em bases cientificas reais.
- Nao substitui revisores humanos.
- Nao garante qualidade metodologica final.
- Nao implementa frontend completo.
- Nao implementa deduplicacao avancada.

## 14. Criterios de aceite

O MVP sera considerado aceito se:

- O ambiente sobe com Docker Compose.
- O PostgreSQL e o pgAdmin ficam acessiveis.
- A API FastAPI inicia localmente.
- Um projeto de revisao pode ser criado.
- Artigos de exemplo podem ser carregados.
- Strings de busca, fontes, datas e filtros podem ser registrados.
- Registros importados podem ser normalizados.
- Duplicados podem ser sinalizados.
- Chunks e embeddings podem ser gerados.
- Uma consulta RAG recupera contexto relevante.
- O ScreeningAgent gera decisao justificada.
- A decisao registra fase, criterio aplicado, evidencia e motivo.
- A decisao e salva no banco.
- A interacao do agente e registrada em `agent_interactions`.
- A tabela de exclusoes ou resumo de selecao pode ser gerada.
- O professor consegue ver o fluxo executado ponta a ponta.

## 15. Metricas de avaliacao

Metricas tecnicas:

- Tempo medio de triagem por artigo.
- Tempo medio de recuperacao RAG.
- Numero de chunks recuperados por consulta.
- Taxa de erros na API.
- Custo por execucao, quando usar API externa.

Metricas funcionais:

- Percentual de decisoes com justificativa.
- Percentual de decisoes com evidencia associada.
- Percentual de decisoes com criterio aplicado.
- Percentual de decisoes com fase F1/F2/F3 registrada.
- Percentual de decisoes marcadas como `uncertain`.
- Concordancia entre decisao do agente e decisao humana.
- Completude da extracao de evidencias.
- Taxa de falso include.
- Taxa de falso exclude.

Metricas de rastreabilidade:

- Percentual de interacoes salvas em `agent_interactions`.
- Percentual de outputs com modelo e parametros registrados.
- Numero de pendencias apontadas pelo AuditAgent.
- Percentual de decisoes reconstruiveis a partir dos logs.

Metricas metodologicas:

- Concordancia agente versus revisor humano por fase.
- Taxa de exclusoes revertidas por revisao humana.
- Percentual de exclusoes com motivo registrado.
- Percentual de afirmacoes da sintese ligadas a estudos ou evidencias.
- Percentual de campos completos no formulario de extracao apos validacao humana.
- Numero de extrapolacoes detectadas pelo AuditAgent.
- Capacidade de reconstruir busca, selecao e extracao a partir dos registros.

## 16. Escopo do MVP e fora de escopo

Dentro do MVP:

- Criar projeto de revisao.
- Carregar artigos de exemplo.
- Registrar estrategia de busca manualmente.
- Registrar fonte, data, filtros e quantidade de resultados.
- Normalizar registros importados.
- Sinalizar duplicados simples.
- Executar selecao F1 com titulo, resumo e metadados.
- Gerar chunks e embeddings.
- Fazer busca RAG usando pgvector.
- Executar agentes com CrewAI.
- Registrar decisoes e interacoes.
- Demonstrar triagem e sintese preliminar.
- Gerar insumos simples de relatorio e transparencia.

Fora do MVP:

- Frontend completo.
- Autenticacao e controle de acesso.
- Busca automatica em PubMed, Scopus, Web of Science ou similares.
- Deduplicacao avancada.
- Avaliacao metodologica completa.
- Exportacao formal em PRISMA.
- Execucao distribuida com filas.
- Deploy em nuvem.

Observacao sobre deduplicacao:

O MVP implementa deduplicacao simples ou assistida por regras, por exemplo com DOI, titulo, autores, ano e fonte. Deduplicacao avancada, com reconciliacao robusta de metadados, permanece fora do escopo.

## 17. Avaliacao do artefato

O MVP pode ser avaliado em tres niveis:

1. Avaliacao funcional: o sistema executa o fluxo ponta a ponta?
2. Avaliacao metodologica: as decisoes sao rastreaveis, justificadas e aderentes ao protocolo?
3. Avaliacao comparativa: as sugestoes dos agentes convergem com decisoes humanas?

Essa avaliacao deve considerar o sistema como artefato de apoio a RSL, nao como substituto do processo humano de revisao.

A avaliacao comparativa podera ser realizada sobre um conjunto pequeno de artigos previamente triados pelo pesquisador, comparando as sugestoes dos agentes com as decisoes humanas registradas.

## 18. Roteiro de demonstracao para o professor

1. Mostrar o Docker com banco e pgAdmin em execucao.
2. Abrir a documentacao da API FastAPI.
3. Criar um projeto de revisao.
4. Registrar pergunta, criterios, fonte, data e string de busca.
5. Carregar um conjunto pequeno de artigos de exemplo.
6. Mostrar registros importados e duplicados sinalizados.
7. Gerar embeddings.
8. Executar triagem F1 com ScreeningAgent.
9. Mostrar decisao, criterio aplicado, fase, evidencia e justificativa.
10. Mostrar o registro no banco.
11. Executar extracao de evidencias em um artigo incluido.
12. Gerar sintese preliminar.
13. Mostrar relatorio simples de transparencia.
14. Mostrar que a decisao humana ainda e necessaria.
