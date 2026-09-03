# RAG visual revisado — 2.4.0-rc.1

Estado: candidata preparada após validação automatizada, isolada e funcional local.
A VPS continua na versão estável 2.3.0 até a publicação da tag da candidata.

## Escopo

- Somente Assistente e benchmark; Relatório Final, extração e embeddings não mudam.
- Opção por projeto, persistida e auditada, desativada por padrão.
- Nenhuma nova imagem é enviada ao provedor durante uma pergunta. São utilizados
  os textos das interpretações já geradas e aprovadas/corrigidas na segunda revisão.
- O artigo precisa continuar incluído; catálogo e interpretação precisam estar
  atuais e aprovados/corrigidos. O SHA-256 do PDF físico deve coincidir com a origem.
- Resumo corrigido substitui a interpretação original: observações e dados brutos
  da IA não são reaproveitados como se tivessem sido aprovados.

## Recuperação e limites

A busca textual híbrida permanece igual quando a opção está desligada. Com a opção
ligada, até seis interpretações com sobreposição de palavras relevantes são
intercaladas aos candidatos textuais antes do reranking compartilhado. O limite
final configurado continua igual. A busca visual desta etapa é lexical, com
normalização de acentos e remoção de palavras comuns; não é busca semântica de
imagens nem OCR adicional. Sinônimos ou tradução entre idiomas podem reduzir o
recall visual. Não se promete melhoria sem medir o Golden Set.

No máximo 2000 interpretações elegíveis são examinadas por projeto/consulta;
catálogos maiores produzem erro explícito. PDFs são conferidos sem cache de hash,
podendo elevar a latência. Não há novos vetores nem alteração da dimensão existente.

Citação textual: `[paper_id, p. 2]`.
Citação visual: `[paper_id, p. 2, visual artifact_id]`.
O detalhe da seleção mostra tipo, legenda, ID da interpretação e página. O registro
de auditoria preserva versão da configuração, hash, revisões e origem do modelo.
A validação determinística confirma a origem da citação, não a veracidade semântica
de cada afirmação. A resposta distingue interpretação de transcrição literal.

PDF/revisão/autorização alterados durante a geração impedem a entrega da resposta.
Mensagens antigas são histórico; se as fontes não puderem ser revalidadas, aparecem
separadas como registro antigo, não como evidência atual.

## Golden Set e comparação

Cadastre julgamentos textuais e visuais separadamente. Uma figura e um trecho da
mesma página são alvos diferentes, sem crédito duplicado. Uma figura revogada,
importada como histórica ou cujo PDF mudou bloqueia o benchmark até rever o gabarito.

Com o uso visual ligado, marque **Comparar somente texto × texto + interpretações
visuais**. Isso executa cada pergunta duas vezes e aumenta o consumo das APIs;
retries e reavaliação de recusa também podem acrescentar chamadas. As duas variantes
usam o mesmo Golden Set. A comparação inclui somente perguntas concluídas nos dois
modos, apresenta exclusões e separa a recuperação visual da regressão textual.
O JSON guarda rankings, configurações, revisões visuais e resultados dos dois modos.
Mudança do catálogo/autorização durante a comparação exige nova execução.

## Persistência e portabilidade

Migração `018_visual_rag.sql`: configuração por projeto e fonte visual opcional nos
julgamentos. Reaplicação das migrações preserva texto e múltiplas figuras por página.
Backup completo preserva configuração e auditoria. A importação de pacote de
reprodutibilidade remapeia os IDs dos julgamentos visuais, mas **não ativa** o uso
visual no novo projeto; os catálogos/interpretações importados continuam históricos.
Após associar os PDFs, recatalogar, interpretar e revisar, ajuste o gabarito para as
fontes atuais e só então ative o recurso.

## Validação manual local

1. Confirme `2.4.0-rc.1`, navegação e diagnóstico operacional.
2. No Assistente, confira que o uso visual começa desligado. Faça uma pergunta textual.
3. Em um projeto com PDF incluído, aprove/corrija um candidato no Catálogo Visual,
   autorize sua interpretação e registre a segunda revisão.
4. Ative e salve o uso visual no Assistente. Pergunte usando termos da legenda/resumo.
   Confira citação com artigo, página e ID visual, a identificação como interpretação
   e o detalhe da seleção. Não é obrigatório recuperar visual em toda pergunta.
5. Desative a opção, recarregue a página e confira a persistência. Outro projeto
   deve permanecer com sua própria configuração.
6. Em um projeto demonstrativo, corrija/rejeite uma interpretação usada anteriormente.
   Confira a separação do histórico antigo e a exclusão em novas respostas.
7. Cadastre ao menos um julgamento textual e um visual, além de uma pergunta de
   recusa. Execute a comparação e confira os rankings e o JSON exportado. Revise
   também a regressão textual, não somente a média combinada.
8. Gere e valide backup. Valide importação/restore somente em ambiente isolado.
   O Relatório Final deve continuar usando seu fluxo textual já validado.

Os testes funcionais locais foram concluídos em 2026-09-03. O piloto na VPS deve
usar somente a tag imutável publicada após o merge da branch de release.
