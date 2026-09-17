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

A candidata deve ser implantada primeiro em usuário único. A ativação multiusuário
só pode ocorrer depois de confirmar operador OIDC estável, convite válido, backup
externo em sucesso e plano de reversão. O roteiro reproduzível está em
[CHECKLIST_RELEASE_V2_6.md](CHECKLIST_RELEASE_V2_6.md) e os detalhes de segurança em
[PILOTO_OIDC_CONTROLADO.md](PILOTO_OIDC_CONTROLADO.md).

Este documento será completado com contagens, horários e resultados sem registrar
e-mails, identificadores OIDC, tokens, chaves ou conteúdo dos projetos.
