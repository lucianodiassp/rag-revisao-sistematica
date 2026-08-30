# Provedores de IA

A linha `2.2` permite usar Google Gemini e OpenAI nas tarefas generativas sem
alterar os agentes científicos. Formulação, triagem, RAG, reranking, auditoria,
extração, qualidade metodológica e relatório podem escolher provedor e modelo
independentemente.

## Escopo desta entrega

- Google Gemini continua sendo o padrão e permanece responsável pelos embeddings.
- OpenAI usa a Responses API somente para geração de texto e JSON.
- O schema vetorial continua em 768 dimensões; trocar apenas o gerador não exige
  reindexar PDFs.
- Não há fallback silencioso entre provedores. Toda tarefa usa exatamente a
  configuração auditada para sua função.
- A configuração permanece no escopo da instalação de usuário único.

## Configuração pela interface

1. Abra **Configuração de IA**.
2. Escolha **Google Gemini** ou **OpenAI** em **Provedor para configurar**.
3. Informe a chave e uma identificação, depois use **Testar e salvar nova chave**.
4. Repita o processo para o outro provedor quando desejar combiná-los.
5. Em **Modelos por função**, selecione o provedor e informe um modelo disponível
   para cada atividade.
6. Salve e confira a tabela **Configuração efetiva** e o histórico de alterações.

A validação consulta somente o catálogo de modelos e não solicita uma geração. A
chave é cifrada antes de ser salva no PostgreSQL, e apenas sua indicação final é
apresentada novamente.

## Fallback pelo ambiente

Em instalações ainda não configuradas pela interface, podem ser usadas:

```ini
GEMINI_API_KEY=valor-secreto
OPENAI_API_KEY=valor-secreto
AI_PROVIDER=google_gemini
AI_DEFAULT_GENERATION_MODEL=modelo-disponivel
AI_EMBEDDING_PROVIDER=google_gemini
AI_EMBEDDING_MODEL=modelo-de-embedding-gemini
AI_EMBEDDING_DIMENSIONS=768
```

O banco cifrado tem precedência sobre as variáveis. Não envie arquivos `.env` ou
chaves reais ao Git.

## Compatibilidade e privacidade

A integração OpenAI usa `POST /v1/responses`, solicita `store=false` e envia modo
JSON quando uma tarefa exige `application/json`. O retorno é convertido ao mesmo
contrato `.text` já utilizado pelos agentes. A referência oficial é o guia de
[geração de texto](https://developers.openai.com/api/docs/guides/text) e o modo JSON
da documentação de
[saídas estruturadas](https://developers.openai.com/api/docs/guides/structured-outputs).

Os registros científicos continuam guardando provedor, modelo, configuração e
função. Credenciais nunca entram nesses metadados nem nas mensagens operacionais.

## Teste recomendado

1. Mantenha inicialmente todas as funções no Gemini e confirme o fluxo atual.
2. Altere somente **Relatório final** para OpenAI e gere uma nova síntese.
3. Confira a identificação do provedor/modelo na rastreabilidade da operação.
4. Altere **Resposta RAG** e faça uma pergunta com citações verificáveis.
5. Execute uma triagem, uma extração e o benchmark com a combinação desejada.
6. Reinicie os contêineres e confirme que credenciais e modelos permanecem ativos.
7. Gere e valide um backup antes de promover uma candidata de release.

## Limites

- disponibilidade de modelos e cotas depende de cada conta e provedor;
- alguns modelos de raciocínio não aceitam temperatura, portanto o parâmetro é
  omitido automaticamente;
- os embeddings OpenAI não estão habilitados nesta versão;
- fallback automático entre provedores pertence a uma evolução posterior e deverá
  ser explícito na auditoria.
