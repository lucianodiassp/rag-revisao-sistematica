# Checklist da candidata v2.2

Este checklist registra os critérios objetivos para publicar `v2.2.0-rc.1` e,
depois do piloto, promover a implementação para `v2.2.0`.

## 1. Integridade da candidata

- [x] A funcionalidade partiu da `main` estável e foi incorporada pelo PR #51.
- [x] A identidade do produto, as imagens Web e os testes usam `2.2.0-rc.1`.
- [x] A suíte automatizada completa termina sem falhas (`237 passed`).
- [x] O Docker local inicia banco, migrações, aplicação, worker e agendador
  saudáveis.
- [x] Os arquivos reais de ambiente e credenciais permanecem fora do Git.

## 2. Compatibilidade e segurança

- [x] As credenciais Gemini e OpenAI são cifradas antes de chegar ao PostgreSQL.
- [x] Reiniciar os contêineres preserva as credenciais e configurações por função.
- [x] Nenhuma chave completa é exibida na interface, nos erros ou nos logs.
- [x] Os embeddings permanecem no Gemini e em 768 dimensões; PDFs existentes não
  precisam ser reindexados.
- [x] A migração histórica de configuração aceita todas as funções atuais.
- [x] O adaptador OpenAI usa a Responses API com armazenamento desativado.

## 3. Validação funcional multiprovedor

- [x] A credencial OpenAI foi criada, salva e validada pela aplicação.
- [x] O relatório final foi gerado com OpenAI.
- [x] O Assistente RAG respondeu com OpenAI preservando `paper_id` e página.
- [x] A triagem com OpenAI produziu decisão, confiança e justificativa coerentes.
- [x] A extração com OpenAI preservou trechos e rastreabilidade das fontes.
- [x] O diagnóstico operacional reconheceu os provedores efetivamente configurados.
- [x] Funções distintas puderam combinar Gemini e OpenAI no mesmo projeto.

## 4. Piloto Web e promoção estável

- [ ] Implantar exatamente a tag `v2.2.0-rc.1` no servidor Web privado.
- [ ] Confirmar login, navegação e versão no menu lateral.
- [ ] Validar no servidor ao menos uma função Gemini e uma função OpenAI.
- [ ] Confirmar RAG e relatório final com referências preservadas.
- [ ] Confirmar diagnóstico operacional sem erros e logs sem segredos.
- [ ] Gerar e validar um backup após o piloto.
- [ ] Promover a identidade para `2.2.0` em branch de release própria.
- [ ] Aprovar o CI, mesclar na `main`, criar a tag e publicar a release estável.

Não reutilize nem mova a tag de uma candidata publicada. Uma correção posterior
deve produzir `2.2.0-rc.2`.
