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

## Terceira entrega: protocolo e PDFs

- alterações de protocolo, coleta, registros de agentes e avaliações exigem papel
  de edição quando existe uma identidade vinculada;
- histórico e impacto do protocolo, status dos PDFs e resultados de avaliação
  aceitam o papel de leitura;
- reavaliar um artigo incluído e iniciar a indexação exigem `editor` ou `owner`;
- o upload de PDF confirma no banco que o artigo pertence ao projeto e continua
  incluído antes da gravação atômica;
- scripts locais de usuário único permanecem compatíveis, enquanto uma execução
  futura em `multi_user` sem identidade falha fechada.

## Quarta entrega: fluxo científico

- consultas de triagem, deduplicação, calibração, limitações, qualidade
  metodológica e evidências visuais exigem ao menos o papel `viewer`;
- decisões humanas, recalibração, revisões, geração de interpretações e execução
  do benchmark exigem `editor` ou `owner`;
- a preferência de uso das interpretações visuais também é isolada por projeto;
- a criação automática do instrumento metodológico padrão exige edição quando o
  projeto ainda não possui instrumento, sem transformar uma leitura em mutação
  autorizada implicitamente;
- testes de contrato interrompem cada grupo antes do acesso ao banco quando a
  autorização central recusa a operação.

## Quinta entrega: agentes e exportações científicas

- formulação, triagem, extração, RAG, auditoria e relatório final verificam o
  papel antes de acessar o projeto ou iniciar consumo no provedor de IA;
- consultas internas dos agentes aceitam `viewer`, enquanto pipelines, respostas,
  julgamentos e relatórios exigem `editor` ou `owner`;
- a leitura dos chunks de um PDF valida também o projeto do artigo, eliminando o
  acesso indireto somente por `paper_id`;
- Golden Set e snapshots PRISMA diferenciam consulta de alterações versionadas;
- a geração do pacote de reprodutibilidade exige associação ativa ao projeto,
  mesmo permanecendo uma exportação somente de leitura e sem segredos;
- testes de contrato bloqueiam esses fluxos antes de consultas, chamadas de IA ou
  criação do arquivo quando a autorização é recusada.

## Sexta entrega: configuração privada por usuário

- credenciais cifradas de Gemini, OpenAI e fontes bibliográficas pertencem à
  identidade autenticada;
- preferências de modelos, parâmetros e fontes também são consultadas e alteradas
  somente no escopo do usuário corrente;
- auditorias de configuração registram o mesmo proprietário, sem armazenar o
  segredo em texto aberto;
- caches de configuração e clientes de IA usam a identidade na chave, impedindo
  que uma sessão reutilize o cliente ou as preferências de outra;
- no modo de usuário único, a primeira identidade ativa adota com segurança os
  registros legados ainda vinculados à instalação;
- no futuro modo multiusuário, chaves e e-mails privados fornecidos ao processo do
  servidor não são fallback compartilhado e não podem ser importados pela tela.

## Limite de segurança atual

Esta entrega **não habilita `RAG_USER_MODE=multi_user`**. O preflight continua
rejeitando esse valor. A fila já propaga e revalida o solicitante, mas várias
operações síncronas especializadas ainda recebem apenas `project_id`. Antes da
ativação serão necessários:

1. aplicar a autorização central às operações administrativas restantes;
2. administração de convites, desativação e transferência de propriedade;
3. testes negativos de isolamento para todas as áreas e arquivos;
4. revisão dos contratos de backup, restauração e suporte operacional.

## Compatibilidade e recuperação

A migração `020_user_project_ownership.sql` é progressiva e não modifica conteúdo
científico; a `021_background_job_requester.sql` acrescenta a autoria das tarefas;
e a `022_user_private_configuration.sql` vincula configurações e segredos cifrados
legados ao único usuário ativo, sem descriptografá-los.
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

## Validação de protocolo e PDFs

1. executar os testes negativos de papel e identidade ausente;
2. editar e salvar um protocolo como proprietário;
3. abrir histórico e impacto do protocolo após atualizar a página;
4. conferir a listagem de PDFs de um projeto existente;
5. confirmar que a indexação continua passando pela fila autorizada;
6. validar que um PDF só pode ser relacionado a artigo incluído no mesmo projeto;
7. executar diagnóstico e gerar um novo backup completo.

## Validação do fluxo científico

1. executar os testes negativos de leitura (`viewer`) e mutação (`editor`);
2. abrir triagem e deduplicação e salvar uma decisão humana existente;
3. conferir calibração da busca, limitações e qualidade metodológica;
4. abrir o catálogo visual, revisar uma interpretação e confirmar o opt-in do RAG;
5. consultar ou executar o benchmark de um projeto autorizado;
6. confirmar que o modo local e a Web privada de usuário único não regrediram;
7. executar a suíte completa, o diagnóstico e validar um novo backup completo.

## Validação dos agentes e exportações

1. executar os testes negativos de leitura e edição antes das chamadas de IA;
2. abrir o Golden Set e consultar o último benchmark sem alterar os dados;
3. executar uma pergunta no Assistente e confirmar resposta e citações;
4. abrir o fluxo PRISMA e gerar ou atualizar o Relatório Final;
5. gerar um pacote de reprodutibilidade do projeto autorizado;
6. confirmar que triagem e extração continuam operacionais pela fila;
7. executar diagnóstico e validar um novo backup completo.

## Validação da configuração privada

1. aplicar a migração `022` duas vezes e confirmar idempotência;
2. verificar que credenciais e configurações legadas pertencem ao usuário ativo,
   sem consultar ou exibir seu conteúdo cifrado;
3. confirmar na tela que Gemini, OpenAI e fontes bibliográficas mantiveram estado,
   modelos e origem após a atualização;
4. testar uma credencial salva de cada grupo e executar uma pergunta no Assistente;
5. reiniciar a aplicação e confirmar persistência e ausência de troca de sessão;
6. executar a suíte completa e confirmar a migração `022` no diagnóstico;
7. gerar e validar um novo backup completo.
