# Checklist da candidata v2.1

Este checklist registra os critérios objetivos para publicar `v2.1.0-rc.1` e
promovê-la posteriormente para `v2.1.0`. A versão estável vigente permanece
`v2.0.1` até que o último gate operacional seja concluído.

## 1. Integridade da candidata

- [x] A funcionalidade partiu da `main` estável e foi incorporada pelo PR #48.
- [x] A identidade do produto, as imagens Web e os testes usam `2.1.0-rc.1`.
- [x] A suíte automatizada completa termina sem falhas.
- [x] Os contratos dos perfis local e Web validam os serviços da aplicação.
- [x] O serviço `backup-scheduler` não publica portas e compartilha apenas os
  volumes necessários.
- [x] Os arquivos reais de ambiente e credenciais permanecem fora do Git.

## 2. Segurança e compatibilidade

- [x] O formato criptografado `.ragbackup` permanece na versão 1.
- [x] A senha do backup não é enviada como metadado nem registrada nos logs.
- [x] Tamanho e SHA-256 são confirmados no destino antes da retenção.
- [x] A retenção só alcança objetos agendados dentro do prefixo configurado.
- [x] Backups manuais e cópias pré-restauração não entram na limpeza automática.
- [x] Um bloqueio compartilhado impede colisões com backup manual ou restauração.
- [x] Configuração inválida interrompe o preflight sem revelar valores sensíveis.

## 3. Piloto Web com destino externo real

- [x] Foi usada uma credencial de serviço limitada ao bucket privado dedicado.
- [x] O preflight Web aceitou a configuração sem expor credenciais.
- [x] A implantação iniciou aplicação, worker, banco, proxy e agendador saudáveis.
- [x] Uma solicitação manual gerou e enviou um backup de aproximadamente 56 MB.
- [x] O objeto remoto teve tamanho e integridade confirmados pela aplicação.
- [x] O Diagnóstico Operacional marcou o backup externo como operacional.
- [x] O objeto foi baixado do destino e validado com a senha de criptografia.
- [x] A ausência de webhook foi apresentada como configuração opcional.

As evidências narrativas do piloto estão em
[VALIDACAO_V2_1_RC1.md](VALIDACAO_V2_1_RC1.md).

## 4. Gate para promoção estável

- [ ] Observar uma execução no horário diário, sem solicitação manual.
- [ ] Confirmar que o novo objeto aparece no destino e atualiza o último sucesso.
- [ ] Confirmar que o Diagnóstico Operacional permanece sem erros após a execução.
- [ ] Gerar e validar um backup final antes de criar a tag estável.
- [ ] Promover a identidade para `2.1.0` em uma branch de release própria.
- [ ] Executar CI, mesclar na `main`, criar a tag `v2.1.0` e publicar a Release.

Não reutilize nem mova a tag de uma candidata já publicada. Qualquer correção após
`rc.1` deve produzir `2.1.0-rc.2`.
