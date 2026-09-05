# Validação da candidata v2.5.0-rc.1

Preparação: 2026-09-05. Release estável anterior: `v2.4.0`.
Escopo: gestão segura do ciclo de vida dos projetos.

## Evidências anteriores à candidata

A implementação foi integrada à `main` pelo PR #62. Antes da preparação:

- 302 testes automatizados aprovados;
- migração `019_project_lifecycle.sql` aplicada e reaplicada no PostgreSQL local;
- dois projetos originais permaneceram ativos e a área temporária ficou limpa;
- Docker local e diagnóstico operacional permaneceram saudáveis;
- projeto acadêmico importado foi arquivado, restaurado, novamente arquivado e
  excluído somente após um backup posterior criado, baixado e validado;
- projetos originais e recibos imutáveis permaneceram disponíveis.

O pacote ensaiado não continha PDFs. O retorno dos PDFs em falha transacional e a
limpeza após commit foram exercitados por testes automatizados.

## Verificação técnica da identidade final

- Identidade esperada: `2.5.0-rc.1` no `VERSION`, interface e quatro serviços Web.
- Migração requerida: `019_project_lifecycle.sql`.
- Backup e pacote acadêmico: formato `1`, sem alteração.
- Embeddings, provedores de IA e fluxo científico: preservados.
- Suíte automatizada da identidade final: **302 testes aprovados** em 2026-09-05.
- Contratos dos Compose local e Web: validados estruturalmente com código zero; o
  perfil Web usou arquivo descartável sem credenciais reais.
- Docker local reconstruído com espera de prontidão; PostgreSQL, aplicação, worker
  e agendador permaneceram saudáveis, e a migração encerrou com código zero.
- Identidade efetiva `2.5.0-rc.1` confirmada dentro do contêiner da aplicação.
- Diagnóstico completo saudável às `2026-09-05T23:04:13Z`, reconhecendo a migração
  `019`, armazenamento, interface, fila vazia, dois provedores de IA e três fontes
  bibliográficas habilitadas.

Comando reproduzível no Windows, usando pasta temporária exclusiva:

```powershell
& .\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp D:\Codex\pytest-rag-v25-rc1-20260905
```

## Piloto Web

Aguardando integração da candidata, publicação da tag imutável e atualização da
VPS conforme [CHECKLIST_RELEASE_V2_5.md](CHECKLIST_RELEASE_V2_5.md).
