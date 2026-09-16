# Piloto OIDC controlado com duas contas

## Objetivo e limites

Validar colaboração real entre o operador atual e uma segunda conta OIDC sem abrir
cadastro público. O piloto usa um projeto escolhido pelo operador, mantém backup
externo obrigatório e pode retornar a `single_user` sem migração reversa do banco.

Durante o ensaio, a conta convidada não cria, importa ou restaura projetos
demonstrativos. Ela trabalha apenas no projeto recebido. O bloqueio existe também
no backend, não apenas na interface.

## Preparação ainda em `single_user`

1. confirme aplicação e diagnóstico saudáveis;
2. gere um backup completo, valide-o e confirme a cópia no armazenamento externo;
3. escolha uma segunda conta controlada e, se o provedor OIDC estiver em modo de
   testes, autorize-a também no próprio provedor;
4. em **Usuários e Acessos**, registre um convite `viewer` para essa conta em um
   projeto apropriado;
5. mantenha somente o e-mail do operador em `RAG_AUTH_ALLOWED_EMAILS`.

No diagnóstico, confirme `oidc_ready_operators: 1`,
`valid_pending_invitations: 1` ou mais, `orphaned_projects: 0` e
`unsafe_pending_invitations: 0`. Esses campos são apenas contadores e não expõem
identidades. Se o operador OIDC não estiver pronto, não ative o piloto.

## Ativação no arquivo privado do servidor

Em `deploy/web.env`, preserve a configuração existente e altere somente:

```env
RAG_USER_MODE=multi_user
RAG_MULTI_USER_PILOT_ENABLED=true
RAG_MULTI_USER_PILOT_ACK=ISOLAMENTO_E_BACKUP_CONFIRMADOS
```

`RAG_EXTERNAL_BACKUP_ENABLED=true` e todas as credenciais do destino externo já
devem estar válidas. A confirmação não é senha; ela evita ativação acidental. Não
copie valores secretos para comandos, logs ou mensagens.

Execute primeiro o preflight e somente depois recrie os serviços:

```bash
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml run --rm preflight
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml up -d --build
sudo docker compose --env-file deploy/web.env -f docker-compose.web.yml ps -a
```

## Validação com duas sessões separadas

Use outro perfil de navegador ou janela anônima para a segunda conta.

1. operador: confirme **Múltiplos usuários**, o aviso do piloto, seus projetos e
   as páginas administrativas de backup e diagnóstico;
2. convidado: entre com o e-mail do convite e confirme que somente o projeto
   compartilhado aparece;
3. como `viewer`, consulte conteúdo e confirme que uma tentativa de alteração é
   recusada;
4. operador: altere o papel para `editor`; convidado: atualize a sessão e registre
   uma alteração científica descartável;
5. confirme que credenciais privadas de IA e fontes do operador não aparecem para
   o convidado;
6. operador: volte o papel para `viewer` e depois revogue a associação;
7. convidado: atualize ou autentique novamente e confirme que não há acesso
   residual ao projeto nem entrada sem outra associação ativa;
8. operador: execute diagnóstico, uma tarefa funcional e um novo backup externo.

## Reversão para usuário único

Se houver comportamento inesperado, altere o arquivo privado para:

```env
RAG_USER_MODE=single_user
RAG_MULTI_USER_PILOT_ENABLED=false
```

Remova ou comente `RAG_MULTI_USER_PILOT_ACK`, execute novamente o preflight e
recrie os serviços. O operador volta a ser a única conta admitida; convites,
associações e auditoria permanecem preservados no banco para investigação, sem
serem usados como porta de entrada em `single_user`.

Não restaure o backup apenas para desligar o piloto. A restauração completa fica
reservada a corrupção ou alteração de dados que realmente exija retorno ao estado
anterior.
