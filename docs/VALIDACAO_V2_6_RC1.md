# Validação da candidata v2.6.0-rc.1

Preparação: 2026-09-16. Release estável anterior: `v2.5.0`.
Escopo: fundação multiusuário e piloto OIDC privado com duas contas conhecidas.

## Evidências anteriores à candidata

A fundação foi integrada progressivamente à `main`, e o gate final do piloto entrou
pelo PR #76. Antes da preparação da candidata:

- 442 testes automatizados foram aprovados;
- migrações `020` a `024` foram aplicadas no PostgreSQL local;
- identidade, propriedade, papéis e solicitante das tarefas permaneceram persistentes;
- configurações privadas, administração global e dados científicos ficaram separados;
- a matriz negativa cobriu duas identidades, dois projetos, revogação e papéis;
- o modo padrão permaneceu `single_user`, com o piloto bloqueado sem dupla confirmação;
- aplicação e serviços locais ficaram saudáveis, com diagnóstico geral `healthy`;
- criação, importação, titularidade, arquivamento e restauração foram validados;
- um backup completo foi criado e validado depois do teste funcional.

## Identidade final da candidata

- Identidade esperada: `2.6.0-rc.1` no `VERSION`, interface e quatro serviços Web.
- Migração mais recente requerida: `024_user_access_administration.sql`.
- Backup e pacote acadêmico: formato `1`, sem alteração.
- Padrão seguro: `single_user`; não existe cadastro público.
- Piloto: ativação dupla, exatamente um administrador na allowlist, entrada da
  segunda conta por convite e backup externo obrigatório.
- Suíte automatizada da identidade final: **442 testes aprovados** em 2026-09-16.
- Docker local reconstruído com espera de prontidão; aplicação, PostgreSQL, worker
  e agendador permaneceram saudáveis, e as migrações encerraram com código zero.
- Identidade efetiva `2.6.0-rc.1` confirmada dentro do contêiner da aplicação.
- Diagnóstico completo saudável em `2026-09-17T00:05:59Z`, reconhecendo a migração
  `024`, armazenamento gravável, fila vazia e integridade de acesso preservada.
  `oidc_ready_operators: 0` é esperado no perfil local e deverá ser `1` na VPS
  antes da ativação do piloto.

## Piloto Web

A tag imutável `v2.6.0-rc.1`, no commit
`e1323e1e889c5b3237de803ca612418d02cb0f0f`, foi publicada como pré-release e
instalada na VPS em 2026-09-16.

- a candidata foi implantada primeiro em `single_user`; preflight, migrações,
  serviços, HTTPS e diagnóstico permaneceram saudáveis;
- o diagnóstico confirmou um operador OIDC pronto, nenhum projeto órfão ou convite
  inseguro e backup externo em estado de sucesso;
- um convite válido para uma segunda identidade conhecida foi registrado sem
  acrescentá-la à allowlist administrativa;
- o preflight aceitou `multi_user` somente depois da ativação dupla e da confirmação
  do backup externo;
- a segunda conta entrou somente pelo convite e visualizou apenas o projeto recebido;
- como `editor`, registrou uma alteração controlada; depois de reduzida a `viewer`,
  manteve leitura, mas não conseguiu salvar novas alterações;
- criação e importação de projetos permaneceram restritas ao operador, e as rotinas
  de backup e diagnóstico não ficaram disponíveis ao colaborador;
- configurações privadas do operador não foram expostas à segunda identidade;
- a revogação retirou o acesso imediatamente, e uma nova autenticação terminou em
  acesso não autorizado, sem acesso residual ao projeto;
- projeto e alteração permaneceram preservados para o operador.

## Backup e reversão

Backups completos foram gerados, baixados e validados antes e depois do piloto. A
cópia externa posterior também foi confirmada no Cloudflare R2 privado.

O arquivo privado voltou a `single_user`, as confirmações temporárias do piloto
foram removidas e o preflight foi repetido. Os serviços retornaram saudáveis, HTTPS,
projetos, alteração e diagnóstico permaneceram disponíveis ao operador, e nenhuma
restauração de dados foi necessária. Usuário, associação revogada e recibos ficaram
preservados para auditoria sem conceder acesso.

Todos os critérios da candidata foram aprovados. Não foi necessária uma
`v2.6.0-rc.2`; a promoção estável pode prosseguir em `release/v2.6.0` sem mover a
tag da candidata.

## Preparação da promoção estável

A branch `release/v2.6.0` atualiza somente identidade e documentação. A suíte
completa permaneceu com **442 testes aprovados**, e os contratos de implantação
incluídos na suíte continuaram válidos. O Docker local foi reconstruído; migrações
encerraram com código zero, todos os serviços ficaram saudáveis, a identidade
`2.6.0` foi confirmada dentro da aplicação e o diagnóstico completo reconheceu a
migração `024` com estado geral `healthy`. A tag estável deve apontar para o merge
dessa branch em `main`, nunca para o commit da candidata.
