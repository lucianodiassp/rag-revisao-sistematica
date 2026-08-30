# Validação da candidata v2.2.0-rc.1

- Data da validação local: 30 de agosto de 2026
- Perfil: Local, usuário único
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

## Gate pendente

A candidata será publicada como pré-release e instalada no servidor Web privado.
A promoção para `2.2.0` depende da repetição dos fluxos essenciais no ambiente real,
da confirmação de logs sem segredos e da geração e validação de um novo backup.
