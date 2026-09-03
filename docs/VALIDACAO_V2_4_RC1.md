# Validação da candidata v2.4.0-rc.1

Preparação: 2026-09-03. Release estável anterior: `v2.3.0`.
Escopo: uso opcional de interpretações visuais revisadas no Assistente e benchmark.

## Evidências anteriores à candidata

A implementação foi integrada à `main` pelo PR #58. Antes da preparação da release:

- 291 testes automatizados aprovados;
- migração `018` reaplicada duas vezes em PostgreSQL isolado;
- conferidos isolamento por projeto, auditoria, Golden Set visual, portabilidade
  histórica, correção/revogação e validação do hash físico do PDF;
- Docker local saudável, migração concluída e diagnóstico operacional aprovado;
- ausência de padrões conhecidos de chaves nos arquivos alterados;
- roteiro funcional completo aprovado pelo pesquisador, incluindo opção desligada,
  recuperação visual, citações, histórico, comparação e preservação do relatório.

Essas evidências autorizam preparar a candidata, mas não substituem a repetição da
suíte com a identidade final nem o piloto da tag no perfil Web privado.

## Verificação técnica da candidata

- Identidade esperada: `2.4.0-rc.1` no `VERSION`, interface e quatro serviços Web.
- Migração requerida: `018_visual_rag.sql`.
- Backup e pacote acadêmico: formato `1`.
- Embeddings: dimensão e provedor existentes preservados.
- Relatório Final: fluxo textual preservado.
- Suíte automatizada da identidade final: **291 testes aprovados** em 2026-09-03.
- Compose local e Compose Web validados estruturalmente com código zero; o arquivo
  de exemplo foi usado sem resolver ou imprimir os segredos de produção.
- Docker local reconstruído com espera de prontidão: aplicação, worker, agendador e
  PostgreSQL saudáveis; migração encerrada com código zero.
- Identidade efetiva `2.4.0-rc.1` confirmada dentro do contêiner da aplicação.
- Diagnóstico completo saudável às `2026-09-03T22:47:05Z`, com migração `018`,
  interface, armazenamento e provedores operacionais e fila sem falhas recentes.

Comando reproduzível no Windows, usando pasta temporária exclusiva:

```powershell
& .\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp D:\Codex\pytest-rag-v24-rc1-20260903
```

## Limites preservados

- A busca visual é lexical sobre interpretações revisadas, não busca semântica de imagens.
- Nenhuma imagem nova é enviada durante perguntas ao Assistente.
- O recurso começa desligado em cada projeto e não é ativado pela importação.
- A validação determinística confirma a origem da citação, não a verdade semântica da afirmação.
- Mudança do PDF, revisão ou autorização invalida a fonte antes da entrega.
- O piloto pode consumir APIs ao executar perguntas e comparações pareadas.

## Piloto Web

Pendente de publicação da tag imutável. Registrar os resultados no
[checklist v2.4](CHECKLIST_RELEASE_V2_4.md) sem anexar segredos, backups ou conteúdo
dos artigos.
