# 🧪 Roteiro de Testes Funcionais (UAT)

**Plataforma de Apoio à Revisão Sistemática (RAG)**

Bem-vindo(a)!

Este documento guia a sua experiência de teste na plataforma. O objetivo é avaliar a fluidez, precisão e utilidade do sistema de triagem e extração de conhecimento baseado em Inteligência Artificial.

**⏱️ Duração estimada:** 15 a 20 minutos.

---

## 📍 Cenário 0: Projeto demonstrativo reproduzível

**Contexto:** Um novo usuário deseja conhecer o fluxo sem configurar chaves ou
executar chamadas externas de IA.

### Passos

1. Abra **Configuração da Pesquisa**.
2. No menu lateral, expanda **Projeto demonstrativo**.
3. Clique em **Criar / abrir demonstração**.
4. Confirme que o seletor identifica o projeto como demonstrativo.
5. Percorra Deduplicação, Triagem, Gestão de PDFs, Matriz de Evidências,
   Avaliação Quantitativa do RAG e Relatório Final.
6. Volte à configuração, marque a confirmação e restaure os dados originais.

### ✅ Critério de Sucesso

* A carga deve funcionar sem solicitar chave de IA.
* O PRISMA deve mostrar 7 registros, 2 duplicatas, 5 artigos únicos, 4 textos
  avaliáveis e 4 estudos na síntese.
* A deduplicação deve mostrar 5 novos artigos e 2 mesclagens por DOI.
* A matriz deve apresentar 4 extrações revisadas e fontes literais atribuídas.
* O Golden Set deve iniciar na versão 1 com 5 perguntas.
* A segunda carga não deve duplicar registros.
* A restauração não deve modificar nenhum outro projeto.

---

## 📍 Cenário 1: Configuração e Coleta

**Contexto:** É necessário iniciar um novo projeto de revisão e definir a estratégia de busca.

### Passos

1. Aceda ao menu lateral e clique em **"Configuração Pesquisa"**.

2. Insira uma pergunta de pesquisa no campo correspondente.

   *Exemplo:* *"Como a IA apoia o diagnóstico em exames de imagem?"*

3. Gere a string de busca (PICO).
4. Na seção de coleta, abra a aba **"Importar BibTeX"** e selecione um arquivo `.bib`.
5. Confira a prévia, as contagens e importe os registros para o projeto ativo.
6. Opcionalmente, use também a aba **"Consultar APIs"** para combinar as duas formas de coleta.
7. Abra **"Deduplicação"** e selecione um candidato pendente.
8. Compare regra, pontuação, DOI, título, autores, ano, fontes e resumos.
9. Mescle um candidato com justificativa e mantenha outro separado, quando houver.

### ✅ Critério de Sucesso

A plataforma deve:

* Gerar a string de busca corretamente.
* Exibir a prévia do BibTeX e informar entradas válidas, sem DOI e sem abstract.
* Registrar os artigos importados e encaminhar os registros sem conflito para a triagem.
* Consolidar automaticamente somente DOI idêntico, preservando a proveniência.
* Manter candidatos por título fora da triagem até a decisão humana.
* Exibir regra, pontuação, evidências comparativas e justificativa da deduplicação.
* Registrar a decisão humana e liberar artigos mantidos separados para a triagem.
* Quando a coleta por API for utilizada, comunicar com a base externa sem erros.

---

## 📍 Cenário 2: Triagem (Human-in-the-Loop)

**Contexto:** O sistema filtrou os artigos, mas a decisão final sobre o que entra na revisão é sempre humana.

### Passos

1. Navegue para o menu **"Triagem"**.
2. Leia a sugestão e a justificativa fornecidas pela Inteligência Artificial para o primeiro artigo da lista.
3. Concorde ou discorde da recomendação clicando em **"Aprovar"** ou **"Rejeitar"**.

### ✅ Critério de Sucesso

* O painel de progresso deve ser atualizado automaticamente.
* O artigo deve transitar para a próxima fase.
* Nenhuma mensagem de erro deve ser apresentada.

### Reavaliação por indisponibilidade do PDF

1. Inclua um artigo na triagem e abra **Gestão de PDFs**.
2. Selecione o artigo ainda sem PDF e abra **"Não consegui obter este PDF"**.
3. Informe a categoria e uma justificativa; escolha **"Voltar para a Triagem"**.
4. Confirme que o artigo reaparece na Triagem com o motivo registrado.
5. Após nova decisão de inclusão, repita o fluxo escolhendo **"Excluir da revisão"**.

O artigo deve sair da lista de PDFs pendentes e cada alteração deve permanecer
registrada em `screening_reassessments`, sem apagar a decisão anterior.

---

## 📍 Cenário 3: Interação com o Motor RAG (O Cérebro da Plataforma)

**Contexto:** Fazer perguntas diretamente à literatura utilizando a base de artigos previamente aprovada.

### Passos

1. No terminal do sistema, observe a execução do Motor de Busca (RAG).
2. No menu lateral, confirme o rótulo **"Assistente de Revisão Sistemática"** e
   faça uma pergunta científica baseada na literatura indexada.
3. Abra **"Como as evidências foram selecionadas"** abaixo da resposta.
4. Compare as posições RRF, IA e final, o score de fusão e a justificativa do reranking.
5. Em seguida, será realizada uma pergunta fora do escopo.

   *Exemplo:* *"Qual é a capital do Brasil?"*

### ✅ Critério de Sucesso

* O sistema deve citar artigo e página no formato `[paper_id, p. página]`.
* Marcadores como `[5]` ou `[36]` devem aparecer identificados como referências bibliográficas internas, e não como páginas.
* O diagnóstico deve mostrar o status do reranking e as posições RRF, IA e final.
* Se o reranking falhar ou estiver desativado, a resposta deve usar o fallback RRF.
* Se a primeira tentativa do reranking falhar, o diagnóstico deve informar a nova
  tentativa e, se necessário, o motivo exato do fallback.
* Uma recusa diante de evidência potencialmente forte deve passar por uma segunda
  leitura conservadora, com o resultado registrado no diagnóstico.
* Perguntas fora do escopo da literatura indexada devem ser recusadas de forma educada.
* Não devem ocorrer alucinações ou respostas sem fundamentação documental.

---

## 📍 Cenário 4: Avaliação Quantitativa do RAG

**Contexto:** Medir a recuperação contra um gabarito definido por uma pessoa, sem
usar a própria IA como fonte da verdade.

### Passos

1. Aceda ao menu **"Avaliação Quantitativa RAG"**.
2. Cadastre uma pergunta que possa ser respondida pelos PDFs indexados.
3. Associe ao menos um artigo, uma página opcional e o grau de relevância.
4. Cadastre uma pergunta fora do corpus e marque **"O sistema deve recusar"**.
5. Execute o benchmark.

### ✅ Critério de Sucesso

* Cada alteração deve aumentar a versão do Golden Set.
* O painel deve comparar RRF, reranking da IA e fusão configurada em Precision,
  Recall, Hit Rate, MRR e nDCG usando exatamente a mesma amostra.
* O painel deve mostrar quantas perguntas entraram na amostra comparável e quantas
  foram excluídas por fallback ou ausência do ranking da IA.
* A calibração deve testar pesos entre 0 e 1 sem realizar novas chamadas à API.
* Com menos de dez perguntas respondíveis, a recomendação deve aparecer como exploratória.
* A pergunta fora do corpus deve contribuir para a taxa de recusa correta.
* O resultado deve informar a versão e o hash do gabarito usado.
* Erros transitórios `429` ou `503` devem acionar novas tentativas com espera progressiva.
* Se uma pergunta esgotar as tentativas, a execução deve registrar a falha e preservar
  os resultados das demais perguntas.
* Os resultados por pergunta devem mostrar tentativas, motivo do fallback e eventual
  recuperação do reranking ou de uma recusa inicial.
* Os arquivos JSON e CSV devem ser exportados corretamente.

---

## 📍 Cenário 5: Auditoria e Relatório Final

**Contexto:** Verificação da transparência do sistema e das métricas de qualidade produzidas pelo Juiz IA (*LLM-as-a-Judge*).

### Passos

1. Aceda ao menu **"Relatório Final"**.
2. Analise o funil quantitativo apresentado no topo da página (**Artigos Únicos × Artigos Aprovados**).
3. Clique em **"Ver detalhes dos testes"** na secção de Auditoria.

### ✅ Critério de Sucesso

* Os gráficos devem refletir corretamente o fluxo de triagem realizado no Cenário 2.
* A tabela de auditoria deve apresentar as avaliações produzidas pelo Agente Avaliador.
* As métricas de qualidade devem estar visíveis e compreensíveis.

---

## 📋 Tabela de Feedback do Avaliador

Após concluir os cenários, por favor, preencha a tabela abaixo e partilhe as suas impressões.

O seu feedback é fundamental para a evolução da pesquisa.

| Cenário de Teste             | Concluído? (Sim/Não) | Dificuldade (1 = Fácil / 5 = Difícil) | Observações e Sugestões |
| ---------------------------- | -------------------- | ------------------------------------- | ----------------------- |
| 1. Configuração e Coleta     |                      |                                       |                         |
| 2. Triagem de Artigos        |                      |                                       |                         |
| 3. Interação com o Motor RAG |                      |                                       |                         |
| 4. Avaliação Quantitativa    |                      |                                       |                         |
| 5. Relatório e Auditoria     |                      |                                       |                         |

---

## 💬 Feedback Geral

**O que achou da confiança transmitida pela plataforma ao exigir a citação rigorosa dos artigos científicos e ao submeter as respostas a uma auditoria independente realizada por um Juiz IA?**

Descreva livremente:

* Pontos positivos.
* Dificuldades encontradas.
* Sugestões de melhoria.
* Funcionalidades desejadas para versões futuras.
