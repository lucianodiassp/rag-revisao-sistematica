# Validação da candidata v2.2.0-rc.1

- Data da validação local: 30 de agosto de 2026
- Perfis: Local e Web privada, usuário único
- Versão estável anterior: `2.1.0`

## Objetivo

Validar geração configurável por função com Google Gemini e OpenAI, preservando
credenciais cifradas, compatibilidade dos embeddings e rastreabilidade científica.

## Validação automatizada e operacional local

- A suíte completa terminou com `237 passed`.
- Banco, migrações, aplicação, worker e agendador iniciaram saudáveis no Docker.
- Uma incompatibilidade idempotente da migração `008` com a função posterior de
  qualidade metodológica foi corrigida e coberta por teste de regressão.
- As configurações OpenAI permaneceram salvas após reiniciar os contêineres.

## Evidências funcionais obtidas

1. A credencial OpenAI foi testada, cifrada e salva pela própria aplicação.
2. O relatório final foi gerado com OpenAI usando `gpt-5-mini`.
3. O Assistente RAG respondeu corretamente com OpenAI e preservou as referências
   de `paper_id` e página.
4. A triagem apresentou decisão, confiança, justificativa e evidência coerentes.
5. A extração manteve trechos literais e rastreabilidade até as fontes.
6. Gemini e OpenAI foram combinados por função sem reindexar os PDFs existentes.
7. O diagnóstico operacional apresentou a configuração efetiva dos provedores.

## Evidências do piloto Web

- A tag imutável `v2.2.0-rc.1` foi implantada com HTTPS e autenticação OIDC.
- Login, navegação, versão e configuração efetiva foram confirmados na interface.
- Gemini e OpenAI executaram funções reais no servidor; RAG e relatório final
  preservaram as referências científicas.
- O Diagnóstico Operacional permaneceu saudável.
- A busca por formatos reconhecíveis de chaves retornou zero nos quatro serviços
  auditados: aplicação, worker, agendador e proxy.
- Um backup posterior ao piloto foi gerado, baixado e validado com sucesso.

## Resultado e decisão

Todos os gates da candidata foram aprovados. A implementação está apta à promoção
estável `v2.2.0`, preservando `v2.2.0-rc.1` como registro imutável do piloto.
