# Gestão segura do ciclo de vida dos projetos — 2.5.x

## Objetivo

Permitir que o pesquisador retire projetos concluídos do trabalho cotidiano sem
perder evidências, e oferecer uma exclusão permanente deliberadamente difícil de
acionar por engano. O fluxo mantém o perfil de usuário único e não introduz
propriedade ou compartilhamento entre pessoas.

## Estados e garantias

### Projeto ativo

- aparece no seletor compartilhado e pode executar todas as funções da revisão;
- pode ser arquivado somente quando não há tarefa em segundo plano ativa;
- o projeto demonstrativo e o último projeto ativo não podem ser arquivados.

### Projeto arquivado

- deixa de aparecer no seletor das páginas operacionais;
- preserva banco, PDFs, protocolo, revisões, resultados e históricos;
- não aceita novas tarefas em segundo plano;
- pode ser restaurado sem perda de informação;
- pode avançar para exclusão permanente somente após um backup completo criado
  depois do arquivamento.

### Exclusão permanente

O botão permanece bloqueado até que todas as condições sejam satisfeitas:

1. o projeto está arquivado e não é a demonstração oficial;
2. nenhuma tarefa está em `queued`, `running` ou `retry_wait`;
3. existe um `.ragbackup` local com data posterior ao arquivamento;
4. o operador confirma que validou o backup e guardou sua senha;
5. o título do projeto é digitado exatamente e a irreversibilidade é confirmada.

A prévia informa artigos, buscas, registros, interações, avaliações, tarefas,
artefatos e interpretações visuais, quantidade e tamanho dos PDFs afetados.

## Atomicidade dos PDFs

Antes de remover o projeto do PostgreSQL, os PDFs identificados pelos artigos do
projeto são movidos para uma pasta temporária confinada ao armazenamento de PDFs.
Se a transação do banco falhar, os arquivos retornam automaticamente aos nomes
originais. Depois do commit, a área temporária é eliminada. Um eventual problema
nessa limpeza posterior não restaura o projeto já excluído, mas gera aviso
operacional e mantém os arquivos fora do diretório normal.

## Auditoria

A migração `019_project_lifecycle.sql` acrescenta os campos de arquivamento e a
tabela `project_lifecycle_events`. O histórico não possui chave estrangeira para o
projeto porque o recibo da exclusão precisa sobreviver à remoção. Ele registra ID e
título do alvo, ação, responsável, data e contagens resumidas, sem conteúdo dos
artigos, credenciais ou chaves.

## Roteiro funcional inicial

Use um projeto descartável, nunca um projeto científico necessário ao teste:

1. atualize o banco pela migração e confirme `Versão 2.5.0-dev` no menu;
2. crie um projeto descartável e mantenha ao menos outro projeto ativo;
3. em **Gestão de Projetos**, confira a prévia e arquive o descartável;
4. confirme que ele desapareceu do seletor das outras páginas;
5. restaure-o e confirme que reapareceu com seus dados intactos;
6. arquive-o novamente e confirme que a exclusão está bloqueada sem novo backup;
7. crie, baixe e valide um backup completo depois do arquivamento;
8. volte à Gestão de Projetos, confirme a prévia, digite o título e exclua;
9. confirme que banco e PDF do projeto foram removidos e que o recibo permanece no
   histórico;
10. tente selecionar a demonstração e o último projeto ativo e confirme as proteções.

O teste de restauração do `.ragbackup` deve ser feito no ambiente isolado já usado
nos ciclos anteriores, sem substituir a instalação principal apenas para exercitar
esta funcionalidade.

## Validação local da primeira implementação

Executada em 2026-09-05 com a versão `2.5.0-dev`:

- um pacote de reprodutibilidade foi importado como projeto isolado e descartável;
- o arquivamento retirou somente esse projeto do seletor operacional;
- a restauração devolveu o projeto com catálogo, interpretações e históricos;
- após novo arquivamento, a exclusão permaneceu bloqueada sem backup posterior;
- um backup completo foi criado, baixado e validado pela aplicação;
- a Gestão de Projetos reconheceu automaticamente a cópia posterior ao arquivamento;
- a confirmação exata e as duas declarações habilitaram a exclusão permanente;
- o projeto importado foi removido, os projetos originais permaneceram disponíveis
  e o recibo de exclusão continuou no histórico imutável.

O pacote ensaiado não possuía PDFs físicos. A remoção e a devolução automática dos
arquivos em caso de falha transacional permanecem cobertas por testes automatizados.
