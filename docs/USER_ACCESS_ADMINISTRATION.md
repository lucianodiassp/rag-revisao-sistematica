# Administração de usuários e acessos

## Escopo desta entrega

A tela **Usuários e Acessos** prepara o compartilhamento por projeto sem tornar a
instalação pública. O perfil `multi_user` somente atravessa o preflight no piloto
explicitamente confirmado; em `single_user`, um convite é uma pré-autorização
registrada no banco.

Um convite contém e-mail normalizado, projeto, papel, validade e autoria. A
aplicação não cria senha, não envia e-mail e não armazena token OIDC. No piloto, a
associação só é aceita depois que o provedor confirma o mesmo e-mail e uma
identidade estável.

## Papéis

- **Proprietário:** administra acesso e titularidade, além de editar o projeto.
- **Editor:** consulta e altera o conteúdo científico permitido.
- **Leitor:** consulta o projeto, sem executar mutações.
- **Operador da instalação:** administra contas, backup e diagnóstico; esse papel
  global não concede acesso automático a projetos.

## Barreiras de segurança

- somente o proprietário administra membros e convites do projeto;
- convites não podem conceder o papel de proprietário;
- a titularidade só vai para um membro e uma conta ativos;
- a transferência ocorre em uma transação e mantém o titular anterior como editor;
- uma conta com projetos próprios não pode ser desativada;
- o operador conectado e o último operador ativo não podem ser desativados;
- toda mutação gera um recibo sem conteúdo científico ou segredo.

## Compatibilidade

Instalações locais e Web privadas de usuário único continuam funcionando como
antes. O único usuário permanece operador e proprietário dos projetos existentes.
Convites pendentes não ampliam a lista fixa do servidor; somente o gate controlado
consulta cada pré-autorização válida no banco.
