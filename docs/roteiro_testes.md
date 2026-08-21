# 🧪 Roteiro de Testes Funcionais (UAT)

**Plataforma de Apoio à Revisão Sistemática (RAG)**

Bem-vindo(a)!

Este documento guia a sua experiência de teste na plataforma. O objetivo é avaliar a fluidez, precisão e utilidade do sistema de triagem e extração de conhecimento baseado em Inteligência Artificial.

**⏱️ Duração estimada:** 20 a 25 minutos.

---

## 📍 Cenário de instalação: Docker Compose completo

**Contexto:** Um novo usuário clonou o repositório e possui somente Git e Docker
Desktop disponíveis.

### Passos

1. Com o Docker Desktop em execução, rode `docker compose up -d --build` na raiz.
2. Execute `docker compose ps -a`.
3. Confirme que `db` está saudável, `migrate` terminou com código `0` e `app`
   está saudável.
4. Abra `http://localhost:8501` e navegue até Configuração da Pesquisa.
5. Reinicie com `docker compose down` e `docker compose up -d`.
6. Confirme que projetos, PDFs e credenciais configuradas continuam disponíveis.

### ✅ Critério de Sucesso

* A interface deve iniciar sem instalação local do Python.
* A aplicação só deve iniciar depois do banco saudável e das migrações concluídas.
* A ausência de `backend/.env` não deve impedir a abertura da interface.
* Os volumes e o diretório `data/pdfs` devem preservar os dados após a reinicialização.

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
   Qualidade Metodológica, Avaliação Quantitativa do RAG e Relatório Final.
6. Volte à configuração, marque a confirmação e restaure os dados originais.

### ✅ Critério de Sucesso

* A carga deve funcionar sem solicitar chave de IA.
* O PRISMA deve mostrar 7 registros, 2 duplicatas, 5 artigos únicos, 4 textos
  avaliáveis e 4 estudos na síntese.
* A deduplicação deve mostrar 5 novos artigos e 2 mesclagens por DOI.
* A matriz deve apresentar 4 extrações revisadas e fontes literais atribuídas.
* A qualidade metodológica deve mostrar 4 avaliações humanas **incertas**, deixando
  claro que os cartões não permitem avaliar o texto integral.
* O Golden Set deve iniciar na versão 1 com 5 perguntas.
* A segunda carga não deve duplicar registros.
* A restauração não deve modificar nenhum outro projeto.

---

## 📍 Cenário de segurança: Backup e restauração

**Contexto:** O usuário precisa preservar toda a instalação ou transferi-la para
outra máquina sem separar manualmente banco, PDFs e chave-mestra.

### Passos

1. Abra **Backup e Restauração**.
2. Crie um backup com uma senha de ao menos 12 caracteres e faça o download.
3. Confirme que uma cópia também aparece em `data/backups/`.
4. Envie o mesmo arquivo, informe uma senha incorreta e tente validá-lo.
5. Informe a senha correta e valide novamente.
6. Confira as contagens do manifesto sem executar a restauração.
7. Em uma instalação de teste, marque a confirmação, digite `RESTAURAR BACKUP` e
   execute a restauração.

### ✅ Critério de Sucesso

* A senha incorreta deve ser rejeitada sem expor conteúdo do arquivo.
* O manifesto deve mostrar projetos, artigos, PDFs e interações esperados.
* A restauração deve criar antes um arquivo `pre-restore-*.ragbackup`.
* Banco, PDFs e credenciais devem voltar ao estado registrado no backup.
* Uma falha deve acionar o retorno automático ao estado anterior.

---

## 📍 Cenário de reprodutibilidade: Exportar um projeto auditável

**Contexto:** O pesquisador deseja compartilhar os métodos, decisões e resultados
de um projeto sem enviar PDFs, credenciais ou o backup completo da instalação.

### Passos

1. Selecione um projeto que possua protocolo, coleta e decisões de triagem.
2. Abra **Relatório Final** e localize **Pacote de Reprodutibilidade do Projeto**.
3. Clique em **Gerar pacote auditável do projeto**.
4. Confirme que as contagens exibidas correspondem ao projeto ativo.
5. Baixe o ZIP e confirme a presença de `README.md` e `manifest.json`.
6. Confira no manifesto o UUID, o título, a versão do protocolo e o SHA-256 dos arquivos.
7. Abra `05_evidencias/matriz_evidencias.csv` no Excel e verifique a acentuação.
8. Quando houver relatório persistido, confirme `08_relatorio/relatorio_final.md`.
9. Confirme que não existem PDFs, vetores, arquivos `.env`, chaves ou senhas no ZIP.
10. Gere o pacote de outro projeto e confirme que não há registros do projeto anterior.

### ✅ Critério de Sucesso

* O ZIP deve conter somente registros vinculados ao projeto selecionado.
* Os hashes e tamanhos do manifesto devem corresponder aos arquivos internos.
* Os CSV devem abrir com acentuação correta.
* Campos sensíveis devem estar ausentes ou marcados como removidos.
* A geração não deve criar, atualizar ou excluir registros no banco.

---

## 📍 Cenário de portabilidade: Importar um projeto auditável

**Contexto:** Outro usuário recebeu o ZIP de reprodutibilidade e deseja reconstruir
o projeto sem substituir sua instalação nem receber credenciais ou PDFs protegidos.

### Passos

1. Abra **Configuração da Pesquisa** e expanda **Importar projeto** no menu lateral.
2. Envie o ZIP original gerado no cenário anterior.
3. Confira título de origem, SHA-256, artigos e decisões apresentados na prévia.
4. Defina um título diferente, aceite a confirmação e importe o projeto.
5. Navegue por protocolo, Deduplicação, Triagem, Matriz de Evidências,
   Qualidade Metodológica, Avaliação Quantitativa e Relatório Final.
6. Em **Gestão de PDFs**, confirme que artigos incluídos aguardam os respectivos PDFs.
7. Tente validar uma cópia do ZIP com algum arquivo interno alterado.

### ✅ Critério de Sucesso

* A importação deve criar um projeto novo, com UUID diferente e sem alterar a origem.
* Contagens, decisões, fontes literais e versões devem corresponder ao manifesto.
* Trechos importados devem permanecer auditáveis, mas não participar da busca RAG.
* PDFs, embeddings e credenciais não devem ser criados pela importação.
* Um pacote alterado deve ser rejeitado antes de gravar qualquer registro.
* Uma falha de persistência deve desfazer toda a importação.

---

## 📍 Cenário 1: Configuração e Coleta

**Contexto:** É necessário iniciar um novo projeto de revisão e definir a estratégia de busca.

### Passos

1. Aceda ao menu lateral e clique em **"Configuração Pesquisa"**.

2. Insira uma pergunta de pesquisa no campo correspondente.

   *Exemplo:* *"Como a IA apoia o diagnóstico em exames de imagem?"*

3. Clique em **Gerar rascunho com IA** e confirme que a versão do protocolo não muda.
4. Revise e edite PICO/PICOS, elegibilidade estruturada, critérios, conceitos e strings.
5. Tente salvar sem motivo ou sem confirmação humana e confira as mensagens de validação.
6. Informe o motivo, marque a confirmação e crie uma nova versão.
7. Abra o histórico e confira a pergunta, os critérios, o PICO/PICOS, a string e o hash.
8. Em um projeto que já possua artigos, confirme o alerta sobre repetição de buscas
   ou reavaliação da triagem.
9. Na seção de coleta, consulte as strings confirmadas por fonte.
10. Abra a aba **Importar BibTeX**, selecione um `.bib`, confira a prévia e importe.
11. Opcionalmente, use **Consultar APIs** para combinar as duas formas de coleta.
12. Abra **Deduplicação**, compare os candidatos e registre as decisões justificadas.

### ✅ Critério de Sucesso

A plataforma deve:

* A IA deve gerar somente um rascunho, sem alterar o protocolo confirmado.
* Campos obrigatórios, período, parênteses e aspas das strings devem ser validados.
* Uma versão só deve ser criada após confirmação humana e justificativa.
* O histórico anterior deve permanecer inalterado e consultável.
* Cada busca deve registrar versão e hash do protocolo em `query_jsonb`.
* Novos pareceres da IA devem registrar a mesma referência e o retrato dos critérios.
* Strings específicas devem ser usadas por fonte; campos vazios devem usar a geral.
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
2. Confira se **Artigos únicos** corresponde à soma de aguardando IA, sem resumo,
   aguardando humano, incluídos, excluídos e marcados como Talvez.
3. Se houver artigos em **Aguardando IA**, execute **"Rodar IA nos Novos Artigos"**.
4. Leia a sugestão, a confiança e a justificativa fornecidas pela IA para o primeiro artigo.
5. Registre a decisão humana como **Incluir**, **Excluir** ou **Talvez**; justifique
   obrigatoriamente uma exclusão ou divergência da sugestão.
6. Troque de projeto e confirme que todas as contagens e o artigo apresentado mudam
   para o escopo selecionado.

### ✅ Critério de Sucesso

* Aguardando IA deve contar apenas artigos com resumo adequado e sem parecer automático.
* Aguardando humano deve contar pareceres da IA ainda sem decisão humana.
* Artigos sem resumo e pendências da deduplicação devem aparecer separadamente.
* O botão da IA deve ficar desabilitado quando não houver artigo processável.
* A mensagem de conclusão só deve aparecer quando todos os artigos tiverem decisão
  humana final e não houver pendência na deduplicação.
* Cada decisão deve atualizar imediatamente as contagens e carregar o próximo artigo.
* O painel de progresso da IA deve ser atualizado automaticamente e sem erros.

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

## 📍 Cenário: Qualidade metodológica rastreável

**Contexto:** O pesquisador precisa avaliar possíveis limitações dos estudos sem
delegar a decisão científica à IA.

### Passos

1. Selecione um projeto com artigos incluídos e PDFs indexados.
2. Abra **Qualidade Metodológica** e confira nome, versão e domínios do instrumento.
3. Em um artigo, gere a sugestão da IA e confira respostas, justificativas, páginas e trechos.
4. Altere ao menos uma resposta ou justificativa, confirme somente as fontes conferidas
   e registre a classificação final humana.
5. Inicie outro artigo manualmente e confirme que o formulário funciona sem chamada à IA.
6. Crie uma nova versão do instrumento alterando uma pergunta e informando o motivo.
7. Confirme que a versão anterior permanece no histórico e que a nova começa sem avaliações.
8. Abra **Relatório Final** e confira o resumo da versão ativa.
9. Gere o pacote de reprodutibilidade e confira os arquivos metodológicos em `06_avaliacao/`.

### ✅ Critério de Sucesso

* Somente artigos incluídos com PDF indexado devem aparecer.
* Uma resposta `yes` ou `no` da IA sem citação literal válida deve virar `uncertain`.
* Sugestão da IA e decisão humana devem permanecer distintas.
* Cada domínio humano deve exigir justificativa, e a decisão geral deve exigir confirmação.
* Trocar o instrumento não deve apagar avaliações históricas.
* Nenhuma classificação deve excluir automaticamente o artigo.
* O relatório deve considerar somente avaliações humanas da versão ativa.

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
