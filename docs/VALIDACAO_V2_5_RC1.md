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

A tag imutável `v2.5.0-rc.1`, no commit
`782e1fe071b03206cd05afe0db9a79f9bd5f0d47`, foi publicada como pré-release e
instalada na VPS em 2026-09-05.

- preflight e migração terminaram com sucesso;
- aplicação, PostgreSQL, worker, agendador e proxy permaneceram saudáveis;
- HTTPS e a identidade `2.5.0-rc.1 · Web privada · Usuário único` foram confirmados;
- o diagnóstico completo reconheceu `019_project_lifecycle.sql`, fila vazia,
  armazenamento saudável, backup externo, dois provedores de IA e três fontes
  bibliográficas, com estado geral saudável;
- um pacote acadêmico descartável foi importado, arquivado, restaurado, novamente
  arquivado e excluído somente após a validação de um backup posterior;
- os dois projetos preservados, o recibo imutável e os fluxos de navegação, RAG,
  relatórios, credenciais e diagnóstico permaneceram íntegros.

## Backup e restauração isolada

Depois do piloto, um backup completo foi criado, baixado e validado. O backup
externo também foi confirmado no Cloudflare R2 privado.

O backup anterior à exclusão foi restaurado pelo Compose isolado na porta `18501`,
sem substituir a aplicação local principal nem a VPS. A restauração recompôs os
dois projetos ativos, o projeto descartável arquivado fora do seletor, seu histórico
de ciclo de vida e os dados dos projetos originais. O ambiente isolado foi encerrado
preservando seus volumes para eventual conferência.

Todos os critérios da candidata foram aprovados; não foi necessária uma
`v2.5.0-rc.2`. A promoção estável pode prosseguir em `release/v2.5.0` sem mover a
tag da candidata.

## Preparação da promoção estável

A branch `release/v2.5.0` atualiza somente a identidade e a documentação da
promoção. A suíte completa permaneceu com **302 testes aprovados**, e os contratos
de implantação incluídos na suíte continuaram válidos. A tag estável deve apontar
para o merge dessa branch em `main`, nunca para o commit da candidata.

## Fechamento da versão estável

A promoção foi integrada à `main` pelo PR #64. A tag anotada `v2.5.0` aponta para
o merge `2319309` e foi publicada como release estável e mais recente.

Na VPS, o preflight reconheceu a identidade `2.5.0` e a atualização preservou os
volumes e as configurações privadas. O diagnóstico final, gerado em
`2026-09-06T01:45:31Z`, apresentou estado geral saudável, migração
`019_project_lifecycle.sql` atualizada, armazenamento gravável, worker ativo, fila
vazia, backup externo em estado de sucesso e credenciais dos dois provedores de IA
disponíveis. O endpoint público retornou `HTTP/2 200`, e a interface confirmou
`Versão 2.5.0 · Web privada · Usuário único`, com projetos e navegação preservados.
