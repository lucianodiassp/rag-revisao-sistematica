# Buscas externas rastreáveis

## Objetivo

Registrar, junto de cada importação BibTeX, a consulta que foi realmente executada
em uma base externa. O registro permite reconstruir a origem do lote sem misturar a
estratégia conceitual geral do protocolo com sintaxes específicas de Web of Science,
Scopus, IEEE Xplore ou outra base.

## Fluxo

1. Confirme a pergunta, os critérios e a estratégia geral na versão do protocolo.
2. Execute a busca na base externa e preserve sua string exatamente como utilizada.
3. Exporte o resultado em BibTeX sem alterar o conteúdo do arquivo.
4. Na aba **Importar BibTeX**, selecione o arquivo e confira a prévia.
5. Registre:
   - base consultada;
   - identificação humana da busca;
   - data da execução;
   - quantidade total mostrada pela base;
   - string exata;
   - filtros aplicados fora da string.
6. Confirme a proveniência e importe o lote.

A quantidade informada pode ser maior que o número de registros exportados quando a
base permitiu baixar apenas uma parte do resultado. Ela não pode ser menor que o
total de entradas presentes no arquivo.

## Dados preservados

A execução fica registrada em `search_queries` com:

- versão e hash do protocolo ativo;
- base e string exata;
- identificação, data, filtros e contagem declarada;
- nome, codificação e SHA-256 do arquivo;
- totais válidos, sem resumo, sem DOI e duplicatas internas;
- resultado da persistência e vínculo dos registros recuperados.

O pacote de reprodutibilidade já exporta `search_queries` e os registros recuperados,
portanto a nova proveniência acompanha o projeto sem alterar o formato do pacote.
Backups completos também preservam os dados porque a estrutura existente do banco é
reutilizada; não há nova migração.

## Compatibilidade

Importações antigas continuam legíveis. Quando não possuem a nova seção de
proveniência, a interface informa que somente o arquivo e o hash estavam disponíveis.
A API interna mantém a forma anterior de importação para testes, scripts e pacotes
legados, mas a interface exige a confirmação dos dados externos para novos lotes.
