# Roadmap da versão 2 Web privada

## Objetivo

Evoluir a aplicação local de usuário único para uma implantação Web privada,
preservando o fluxo científico, os formatos de backup e os pacotes de
reprodutibilidade da versão 1.

A primeira entrega Web continuará com **um único usuário autorizado**. O suporte a
múltiplos usuários será uma evolução posterior e exigirá autorização por recurso,
isolamento por proprietário e revisão das rotinas administrativas.

## Estratégia de branches

- `main`: versão estável publicada, atualmente `v2.1.0`.
- `v2-web`: linha histórica usada para integrar a primeira versão Web.
- novas branches: correções e funcionalidades passam a partir da `main`.

O ciclo inicial da v2 foi encerrado. A partir da versão estável, pull requests de
manutenção e evolução usam **`main` como branch de destino**.

## Etapas

### 1. Autenticação OIDC para usuário único

Branch: `feature/v2-autenticacao`

Estado: **implementada e validada**.

- Usar a autenticação OIDC nativa do Streamlit.
- Exigir login quando `RAG_DEPLOYMENT_PROFILE=web_private`.
- Restringir o acesso a uma lista explícita de e-mails autorizados.
- Não armazenar senha do usuário no banco da aplicação.
- Manter `RAG_DEPLOYMENT_PROFILE=local` funcionando sem login.
- Exibir identidade do usuário e permitir logout.
- Testar acesso local, não autenticado, autorizado e não autorizado.

Critério de aceite: nenhuma página ou dado do sistema pode ser exibido no perfil
Web privado antes da autenticação e da verificação da lista de acesso.

### 2. Configuração segura de produção

Branch: `feature/v2-configuracao-producao`

Estado: **implementada e validada em servidor com domínio público**.

- Separar o Compose local da sobreposição Web.
- Retirar credenciais padrão do perfil Web e exigir segredos externos.
- Publicar somente a porta necessária da aplicação.
- Documentar HTTPS, domínio, proxy reverso e variáveis obrigatórias.
- Adicionar verificações de inicialização para configurações inseguras.

Critério de aceite: o perfil Web deve falhar de forma clara quando um segredo ou
parâmetro obrigatório estiver ausente, sem usar valores padrão inseguros.

### 3. Armazenamento persistente e recuperação

Branch: `feature/v2-armazenamento-pdfs`

Estado: **implementada e validada**.

- Definir volumes persistentes para banco, PDFs, backups e chave-mestra.
- Validar limites de upload e espaço disponível.
- Preservar compatibilidade com o backup `.ragbackup` da v1.
- Documentar backup externo e recuperação da implantação.

Critério de aceite: uma recriação dos contêineres não pode perder dados e um backup
validado deve restaurar a instalação em ambiente limpo.

### 4. Processamento resiliente

Branch: `feature/v2-processamento-assincrono`

Estado: **implementada e validada**.

- Mapear operações demoradas de busca, indexação, extração, relatório e benchmark.
- Evitar que uma desconexão do navegador perca o estado de uma operação.
- Registrar progresso, falhas e possibilidade de nova tentativa.
- Definir limites de concorrência e consumo das APIs de IA.

A implementação utiliza uma fila no PostgreSQL e um processo separado, limitado a
uma operação por vez no perfil de usuário único. Coleta, indexação, extração,
relatório e benchmark preservam estado, progresso, falhas e tentativas mesmo quando
a página é atualizada ou fechada. Erros transitórios de provedor podem ser repetidos
automaticamente; falhas definitivas oferecem nova tentativa manual.

Critério de aceite: tarefas longas devem continuar rastreáveis após atualização ou
reconexão da interface.

### 5. Observabilidade e operação

Branch: `feature/v2-observabilidade`

Estado: **implementada e validada**.

- Logs estruturados sem chaves, tokens ou conteúdo sensível.
- Identificação da versão e do perfil em eventos operacionais.
- Health checks de aplicação, banco e migrações.
- Guia de diagnóstico, atualização e retorno à versão anterior.

A implementação registra eventos operacionais em JSON com versão, perfil e categoria,
mantém sinais de vida da aplicação e do worker no PostgreSQL, verifica migrações e
volumes e disponibiliza um diagnóstico seguro na interface e na linha de comando.
Falhas recentes são traduzidas em ações específicas sem expor credenciais ou conteúdo
dos projetos.

Critério de aceite: o operador deve conseguir distinguir falha de configuração,
banco, armazenamento, provedor de IA e fonte bibliográfica.

## Resultado do primeiro ciclo da v2

As cinco etapas técnicas do primeiro ciclo e o gate local de integridade,
compatibilidade e validação funcional foram concluídos. A `2.0.0-rc.1` foi usada
no primeiro piloto com domínio, HTTPS e callback OIDC reais. Os ajustes encontrados
nesse ensaio formaram a `2.0.0-rc.2`. A repetição dos gates identificou conteúdo
sensível nos logs do proxy e do worker. A correção foi aplicada, revalidada com
todos os contadores em zero e forma a `2.0.0-rc.3`, antes da publicação estável
`v2.0.0`.

O procedimento e as evidências esperadas estão no
[Checklist da candidata v2](CHECKLIST_RELEASE_V2.md). A terceira candidata passou
na verificação final em servidor real e tornou a `v2-web` elegível para incorporação
à `main` e publicação da versão estável `v2.0.0`.

## Fora do primeiro ciclo da v2

- Cadastro público e autoatendimento.
- Múltiplos usuários e compartilhamento de projetos.
- Cobrança, planos ou limites por usuário.
- Execução distribuída e escalabilidade horizontal.

Esses itens continuam possíveis, mas pertencem a ciclos posteriores ao
endurecimento operacional da Web privada de usuário único.

## Radar pós-release

1. `v2.0.x`: integração contínua, documentação pós-release e operação mais segura.
2. `v2.1.x`: backup externo agendado, retenção e alertas operacionais — concluído e
   validado em destino S3 real, incluindo execução automática diária.
3. `v2.2.x`: provedores adicionais de IA — concluído e validado nos perfis local e
   Web privado, com Gemini e OpenAI selecionáveis por função.
4. ciclo posterior: instrumentos científicos adicionais e interpretação de tabelas
   e figuras dos PDFs.
5. `v3.x`: propriedade por usuário, compartilhamento de projetos e escalabilidade.
