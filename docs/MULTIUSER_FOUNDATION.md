# Fundação multiusuário da v2.6

## Objetivo

Preparar identidade persistente e propriedade de projetos sem transformar a
instalação privada atual em serviço público antes que todas as barreiras de
autorização estejam prontas. A versão estável `v2.5.0` continua sendo a referência
operacional; esta evolução começa em `2.6.0-dev`.

## Primeira entrega

- `application_users` registra provedor, sujeito OIDC estável, e-mail normalizado,
  nome de exibição, estado e último acesso; tokens não são persistidos.
- `project_memberships` associa cada projeto a um proprietário e já admite os
  papéis futuros `owner`, `editor` e `viewer`.
- no perfil local existe uma identidade determinística da instalação;
- no perfil Web, `iss` e `sub` identificam a conta; o fallback por e-mail existe
  apenas para compatibilidade no modo de usuário único;
- ao atualizar uma instalação existente, o único usuário adota somente projetos
  que ainda não possuam associação ativa;
- projetos criados, demonstrativos restaurados e pacotes importados recebem o
  proprietário corrente;
- seletor, consulta principal e gestão do ciclo de vida filtram os projetos pela
  associação ativa;
- recibos de arquivamento, restauração e exclusão ficam vinculados ao proprietário
  para continuarem privados após a remoção do projeto.

## Limite de segurança desta etapa

Esta entrega **não habilita `RAG_USER_MODE=multi_user`**. O preflight continua
rejeitando esse valor porque várias operações especializadas e o worker ainda
recebem apenas `project_id`. Antes da ativação serão necessários:

1. autorização central por papel em todas as leituras e mutações de projeto;
2. propagação segura do usuário que originou cada tarefa para o worker;
3. escopo por usuário para credenciais e configurações sensíveis;
4. administração de convites, desativação e transferência de propriedade;
5. testes negativos de isolamento para todas as áreas e arquivos;
6. revisão dos contratos de backup, restauração e suporte operacional.

## Compatibilidade e recuperação

A migração `020_user_project_ownership.sql` é progressiva e não modifica conteúdo
científico. Backups completos incluem as novas tabelas. Pacotes acadêmicos não
transportam identidade pessoal: ao serem importados, pertencem ao usuário que
executou a importação. O modo local e a Web privada de usuário único devem manter
os mesmos projetos e funcionalidades após a atualização.

## Validação inicial

1. aplicar a migração `020` duas vezes e confirmar idempotência;
2. abrir a aplicação local e confirmar `Versão 2.6.0-dev · Local · Usuário único`;
3. conferir que todos os projetos existentes continuam no seletor;
4. criar ou importar um projeto e confirmar sua associação como proprietário;
5. arquivar e restaurar esse projeto sem afetar os demais;
6. reiniciar a aplicação e confirmar que identidade e associações persistem;
7. gerar e validar um backup completo;
8. manter o preflight Web rejeitando `multi_user` até a conclusão do escopo.
