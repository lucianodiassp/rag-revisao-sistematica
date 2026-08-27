# Versionamento e linhas de evolução

## Versões independentes

O projeto mantém separadas as seguintes identidades:

| Identidade | Exemplo | Responsabilidade |
|---|---:|---|
| Aplicação | `2.0.0` | Funcionalidades e compatibilidade do produto |
| Migração do banco | `013` | Evolução progressiva do schema PostgreSQL |
| Formato do backup | `1` | Leitura e restauração do `.ragbackup` |
| Pacote de reprodutibilidade | `1` | Exportação e importação acadêmica |
| Protocolo científico | `v3` | Histórico metodológico dentro de cada projeto |

A versão da aplicação fica no arquivo `VERSION` e segue o Versionamento Semântico:

- `MAJOR`: mudança incompatível ou nova geração do produto;
- `MINOR`: funcionalidade compatível;
- `PATCH`: correção compatível.

## Linhas do produto

- `v1.x`: instalação local e de usuário único.
- `v2.x`: implantação Web privada, inicialmente de usuário único.

A v2 deve preservar o modo local sempre que possível. O perfil efetivo é informado
por `RAG_DEPLOYMENT_PROFILE=local|web_private`; o modo de usuários, por
`RAG_USER_MODE=single_user|multi_user`.

## Estado atual

- `v1.0.0`: primeira versão local estável, etiquetada e publicada no GitHub.
- `v2-web`: linha de integração usada na construção da versão Web.
- `2.0.0-rc.1`: primeira candidata, usada no piloto Web real.
- `2.0.0-rc.2`: candidata corrigida após o primeiro piloto público.
- `2.0.0-rc.3`: candidata com o gate de privacidade dos logs aprovado.
- `2.0.0`: versão estável local e Web privada, inicialmente de usuário único.

O sufixo `-rc.N` identificou as candidatas e impediu que fossem confundidas com a
Release estável `v2.0.0`.

## Fluxo concluído da v1.0.0

1. Mesclar a branch de versionamento na `main`.
2. Atualizar a `main` local e executar a suíte completa.
3. Criar e validar um backup operacional.
4. Criar uma tag anotada no commit da `main`:

   ```bash
   git tag -a v1.0.0 -m "RAG para Revisão Sistemática v1.0.0 — Local"
   git push origin v1.0.0
   ```

5. Criar a GitHub Release usando a seção `1.0.0` do `CHANGELOG.md`.
6. Criar `v2-web` a partir da `main` já etiquetada.

## Fluxo de desenvolvimento concluído da v2

As funcionalidades da v2 foram desenvolvidas em branches pequenas, direcionadas à
branch de integração `v2-web`, por exemplo:

- `feature/v2-autenticacao`;
- `feature/v2-configuracao-producao`;
- `feature/v2-armazenamento-pdfs`;
- `feature/v2-processamento-assincrono`;
- `feature/v2-observabilidade`.

A `v2-web` foi incorporada à `main` depois da validação integral, e a tag `v2.0.0`
foi criada no commit integrado. Novas correções e funcionalidades devem partir da
`main`; a antiga branch de integração pode permanecer apenas como histórico.

Antes da versão estável, a linha passou por uma candidata `2.0.0-rc.1`. A candidata
foi identificada e etiquetada depois dos testes locais, da restauração de um
backup v1 em ambiente limpo e da validação funcional. O piloto com domínio, HTTPS
e OIDC reais usou exatamente essa tag. As correções posteriores geraram novas
candidatas (`rc.2`, `rc.3`), sem mover ou reutilizar tags já publicadas.

O planejamento incremental, os critérios de aceite e os itens fora do primeiro
ciclo estão detalhados em [ROADMAP_V2_WEB.md](ROADMAP_V2_WEB.md).
O gate de promoção está detalhado em
[CHECKLIST_RELEASE_V2.md](CHECKLIST_RELEASE_V2.md).

## Compatibilidade e retorno

- Migrações do banco são progressivas e não devem ser revertidas manualmente.
- Antes de testar a v2, deve-se criar um backup v1 e usar uma cópia dos dados.
- O código v1 não deve abrir um banco já migrado para a v2 sem validação explícita.
- Uma restauração da v1 deve usar o backup criado antes da migração.
- Correções críticas da linha v1 podem sair de `release/1.x` e ser incorporadas à v2.
