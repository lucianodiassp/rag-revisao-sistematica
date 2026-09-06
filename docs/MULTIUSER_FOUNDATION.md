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

## Segunda entrega: autorização da fila

- uma única função central verifica usuário ativo, associação ativa e papel mínimo;
- `viewer` pode consultar o andamento, enquanto iniciar ou repetir tarefas exige
  `editor` ou `owner`;
- cada nova tarefa guarda `requested_by_user_id`, sem copiar e-mail ou token;
- antes da execução, o worker recupera e vincula novamente a identidade solicitante;
- uma associação revogada ou usuário desativado impede a execução da tarefa;
- a migração `021_background_job_requester.sql` associa tarefas históricas ao
  proprietário ativo quando essa relação já existe.

## Limite de segurança atual

Esta entrega **não habilita `RAG_USER_MODE=multi_user`**. O preflight continua
rejeitando esse valor. A fila já propaga e revalida o solicitante, mas várias
operações síncronas especializadas ainda recebem apenas `project_id`. Antes da
ativação serão necessários:

1. aplicar a autorização central às demais leituras, mutações e arquivos;
2. escopo por usuário para credenciais e configurações sensíveis;
3. administração de convites, desativação e transferência de propriedade;
4. testes negativos de isolamento para todas as áreas e arquivos;
5. revisão dos contratos de backup, restauração e suporte operacional.

## Compatibilidade e recuperação

A migração `020_user_project_ownership.sql` é progressiva e não modifica conteúdo
científico; a `021_background_job_requester.sql` acrescenta a autoria das tarefas.
Backups completos incluem as novas estruturas. Pacotes acadêmicos não
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

## Validação da autorização da fila

1. aplicar a migração `021` duas vezes e confirmar idempotência;
2. confirmar que tarefas anteriores receberam o proprietário atual;
3. iniciar uma tarefa e verificar que ela registra o solicitante;
4. confirmar que a tarefa conclui normalmente com associação de proprietário;
5. simular `viewer`, associação revogada e usuário desativado nos testes negativos;
6. executar a suíte completa e o diagnóstico operacional;
7. repetir uma tarefa funcional e validar um novo backup completo.
