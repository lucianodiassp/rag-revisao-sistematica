# Validação da candidata v2.1.0-rc.1

- Data do piloto: 29 de agosto de 2026
- Perfil: Web privada, usuário único
- Versão estável anterior: `2.0.1`

## Objetivo

Validar que o novo backup externo reduz o risco de perda simultânea do VPS e das
cópias de recuperação, preservando o formato `.ragbackup` v1 e sem expor segredos.

## Ambiente e configuração

- Aplicação executada em VPS com domínio e HTTPS reais.
- Destino S3 compatível em provedor independente, bucket privado dedicado.
- Credencial de serviço com acesso de leitura e escrita limitado ao bucket.
- Configuração mantida exclusivamente no arquivo seguro e ignorado pelo Git.
- Agendamento diário às `06:00 UTC`, retenção local 3 e retenção externa 14.
- Webhook de alerta deliberadamente não configurado por ser opcional.

Nenhum identificador de credencial, endpoint, token ou senha integra este registro.

## Validação automatizada da candidata

- A suíte completa terminou com `229 passed`.
- Os contratos do Docker Compose local e Web foram aceitos.
- Os arquivos reais de ambiente e segredos permaneceram fora do Git.
- A identidade `2.1.0-rc.1` foi confirmada pela fonte única de versão e pelos
  contratos das imagens Web.

## Evidências obtidas

1. O preflight concluiu sem erros e a imagem de desenvolvimento foi construída.
2. Aplicação, worker, banco, proxy e agendador iniciaram saudáveis.
3. A interface reconheceu o destino S3, horário e políticas de retenção.
4. Uma solicitação manual produziu um `.ragbackup` de 55,9 MB.
5. O serviço enviou o arquivo e confirmou tamanho e SHA-256 no destino.
6. O objeto apareceu no prefixo privado configurado.
7. O Diagnóstico Operacional marcou o backup externo como operacional.
8. O arquivo foi baixado diretamente do destino e validado pela aplicação com a
   senha de criptografia, sem executar restauração desnecessária.

## Resultado e decisão

O fluxo manual ponta a ponta foi aprovado. A implementação está apta a receber a
identidade `2.1.0-rc.1` e ser publicada como pré-release.

A promoção para `2.1.0` permanece condicionada à observação de ao menos uma
execução automática diária, à confirmação do novo objeto remoto e à permanência do
diagnóstico operacional sem erros. Uma falha deve gerar correção e nova candidata,
sem mover a tag `v2.1.0-rc.1`.
