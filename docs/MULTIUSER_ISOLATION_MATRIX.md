# Matriz de isolamento multiusuário

## Objetivo

Demonstrar que identidade, associação, papel por projeto e papel global são
barreiras independentes. Esta etapa fortalece a fundação da v2.6, mas ainda não
habilita `RAG_USER_MODE=multi_user` em produção.

## Matriz de autorização

| Identidade | Ler projeto associado | Alterar conteúdo | Administrar projeto | Administrar instalação |
|---|---:|---:|---:|---:|
| Leitor (`viewer`) | Sim | Não | Não | Não |
| Editor (`editor`) | Sim | Sim | Não | Não |
| Proprietário (`owner`) | Sim | Sim | Sim | Não |
| Operador sem associação | Não | Não | Não | Sim |
| Associação revogada | Não | Não | Não | Conforme papel global |
| Sem identidade em `multi_user` | Não | Não | Não | Não |

O operador só acessa conteúdo científico quando também possui uma associação
ativa no projeto. Da mesma forma, o proprietário de um projeto não recebe acesso
automático a backup, restauração, diagnóstico ou administração de contas.

## Superfícies protegidas

- listagem, seleção e detalhes dos projetos;
- criação comum, restauração da demonstração e importação de pacote acadêmico;
- protocolo, buscas, triagem, PDFs, catálogo visual e avaliações;
- agentes de IA, fila, relatório, PRISMA, Golden Set e exportação reprodutível;
- convites, membros, transferência de titularidade e ciclo de vida;
- backup completo, restauração, backup externo e diagnóstico operacional.

As operações de projeto passam pela autorização central com papel mínimo. As
operações globais passam pela revalidação do operador. Criações que ainda não têm
um `project_id` exigem identidade ativa e gravam o proprietário na mesma transação.

## Provas automatizadas

`tests/test_multi_user_isolation_matrix.py` executa a combinação de duas pessoas,
dois projetos, três papéis, operador global, associação revogada e ausência de
identidade. Os contratos especializados comprovam que a recusa acontece antes de
banco, arquivo ou provedor de IA. `tests/test_project_lifecycle.py` verifica que
até a prévia de exclusão exige proprietário antes de tocar no banco ou nos PDFs.

## Limite desta etapa

A matriz testa as decisões e fachadas do backend de forma determinística. Ainda é
necessário realizar um piloto Web controlado com duas contas OIDC reais, incluindo
convite, primeiro login, troca de papel, revogação e nova autenticação. O preflight
continua bloqueando o modo multiusuário até esse piloto e a decisão operacional de
liberação.
