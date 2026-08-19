# CHECKPOINT — estado do projeto (atualizado em 19/08/2026)

Leia junto com `AGENTS.md`. 34 testes passando. Git limpo e pushado (commit 92b1783).

## Rodada de 19/08/2026 (feedbacks do uso real, todos implementados)

- **Kit LME = 1 PDF único** (tipo `kit_lme`): LME + N receitas + termo + relatório
  concatenados; gera e abre direto para imprimir 1 vez; regenerável do banco.
- **Receitas da farmácia: 1/6/12** (radio no LME; cada receita = 2 vias/folhas;
  padrão 6 → 12 folhas).
- **Termo da demência COMPLETO**: checkbox do fármaco, escolaridade, FOLHA DO MEEM
  embutida preenchida por domínios (distribuição típica de DA a partir do total —
  `_distribuir_meem` em app/services/termos.py; soma sempre confere; conferir antes
  de assinar), CDR, Local/Data e carimbo nas 3 páginas. Outros termos copiados
  ganham carimbo por âncora "Assinatura" (dinâmico via pdfplumber).
- **Posologia recalcula quantidade** (app/static/posologia.js, parser pt-BR:
  "3 cp à noite"→90, "2-0-2"→120, "8/8h"→90, "5 x ao dia", "1 + ½"; recusa
  mL/gotas/adesivos): alimenta os 6 meses do LME e o texto da receita. Qtd manual
  também recalcula o texto. Bidirecional nas duas telas.
- **Medicação e apresentação 100% digitáveis**: apresentação virou input+datalist
  (escolhe do catálogo ou digita livre); medicação livre explícita no placeholder.
- **CID**: chips por MEDICAMENTO (campo `cids` no seed/DB, 37 fármacos) com
  descrição; clicar no chip sempre atualiza o nome do diagnóstico; indicação única
  auto (G40.1 / G30.1 tardio), múltipla pergunta (gaba, azatioprina, IVIG, toxina);
  equivalências F00=G30, G51=G24, G82=G81.
- **Escalas nos dados da IA**: MEEM/CDR/escolaridade/EDSS/LANSS/EVA visíveis entram
  na anamnese/relatório gerados por IA.
- **Imprimir selecionados** (checkboxes do histórico) além do kit de hoje.
- IA: nome do paciente NUNCA vai à API; fecho INSS máximo "retorno programado, sem
  alta até o momento"; anamnese com roteiro obrigatório por doença (funciona com
  poucas palavras, sem inventar números).

## Ajustes finos após teste ao vivo (últimos commits do dia)

- Carimbo com fundo TRANSPARENTE (imagem processada) e maior: 44mm na receita,
  35mm nos quadros 17/23 do LME, sobre a linha do TER — sobrepõe como carimbo real.
- LME: medicamentos desenhados como conteúdo da página (campos Tx/dropdowns não
  renderizam em todos os leitores); widgets de tela ocultados (F=2).
- CIDs POR MEDICAMENTO no catálogo (campo `cids`, 37 fármacos): chips com descrição;
  indicação única auto (G40.1 / G30.1 tardio); múltipla pergunta (gaba G40×R52,
  azatioprina G70×G35, IVIG, toxina). Equivalências: F00=G30, G51=G24, G82=G81.
- Termo segue o CID (gaba+R52 → termo de dor, não epilepsia); R52 abre LANSS/EVA
  (padrão 21/8), obrigatórios, salvos e injetados na anamnese.
- IA: nome do paciente NUNCA vai à API; fecho do INSS limitado a "retorno programado,
  sem alta até o momento"; anamnese com roteiro por doença (funciona com poucas
  palavras, sem inventar números/datas).
- Kit LME gera receita com posologia por linha; "imprimir kit de hoje" no paciente.
- Exclusões: por documento, selecionados, todo o histórico, ou paciente inteiro.

## Funcionando (testado ao vivo pelo usuário)

- **Receitas**: controle especial/comum, posologias por chips, COM/SEM data (sem data =
  papel sem campo), guia de folhas (controlada = 2 folhas/mês pois a farmácia retém 1;
  UBS comum = 1 folha a cada 2 meses), avisos de onde retirar (REMUME/CEAF/comercial),
  repetir, copiar para outro paciente, deixar salvo com PDF sob demanda.
- **Kit LME**: LME oficial preenchido (medicamentos desenhados como conteúdo da página —
  widgets/dropdowns ocultados pois não renderizavam) + receita do medicamento com
  posologia por linha + TER preenchido (nome, CNS, data, checkbox do fármaco, carimbo) +
  relatório alto custo opcional (IA). CID + descrição automáticos ao clicar na medicação;
  escalas MEEM/CDR/EDSS obrigatórias conforme PCDT, salvas e reaproveitadas; anamnese
  reaproveitada da lme_dados em toda renovação. Volta ao paciente com "imprimir kit".
- **Carimbo digital**: senha `carimbo` (mestra = telefone, ambas no .env), válida 24h,
  checkbox padrão dentro da janela; aplicado em receita/LME/TER/relatórios/exames.
- **Impressão**: SumatraPDF portátil (tools/, fora do git), fila com parada no erro,
  retomar/reimprimir folha específica/reimprimir tudo/cancelar, seleção de impressora
  (HP 3015). Página /impressao.
- **Relatório INSS com IA** (GPT-5.6 Sol medium): prompt-base = arquivo do usuário em
  Prompts principais (editável lá), instruções extras por geração, regenerar mais
  conciso/imparcial, 2-3 CIDs sugeridos, PDF previdenciário paginado com identificação,
  sem travessões/frases genéricas. Reaproveitável do histórico.
- **Pedido de exames**: painéis por medicamento, datas +3/6/9/12 meses (1 folha por
  data), JCV nunca é pedido (aviso: feito externamente).
- **Estatísticas** (/estatisticas): meds atuais por paciente, ranking de uso, nº de
  LMEs e próxima renovação (+6 meses). Tags/diagnósticos-chave editáveis na receita e
  extraídos dos relatórios via gpt-5.6-luna (melhor esforço).
- **Sistema leve**: PDFs > 7 dias apagados e regenerados sob demanda (qualquer tipo);
  excluir paciente/documento; backup diário + mensal em M:/backup-sistema.

## Constantes/locais importantes

- `.env` local: dados do médico, CNES, OPENAI_API_KEY, senhas do carimbo, impressora.
- Carimbo: `templates/assets/carimbo.png` (origem: assinatura-digital-thales-com-carimbo.png na raiz do M:).
- LME oficial em branco: `templates/lme/lme_oficial.pdf`; fichas SES-SP: `templates/requisitos-sp/`.
- TER epilepsia usado: pasta TERMOS DE CONSENTIMENTO (campos AcroForm mapeados em app/services/termos.py).

## Próximos passos sugeridos

1. TERs restantes preenchíveis por campo (miastenia/IVIG/botox/gaba-dor hoje são
   copiados com carimbo por âncora; epilepsia e demência já saem completos).
2. Folha EVA/LANSS preenchida (kit de gabapentina-dor): modelo em TERMOS DE
   CONSENTIMENTO/ESCALA_evas_lanss (flat, precisa overlay; padrão LANSS 21, EVA 8).
   Folha EDSS preenchida para EM.
3. Formulários estaduais MG/GO (flat PDFs — overlay ou recriação).
4. Baixar fichas SES-SP dos demais fármacos (demência, EM, toxina, pramipexol...).
5. Se o carimbo do termo de demência sair deslocado na prática, ajustar as
   coordenadas em _preencher_termo_demencia (pg2: 230,598 / pg3: 200,78 / pg5: 200,140).

## Avisos

- Servidor sem auto-reload: fechar e reabrir INICIAR-RECEITAS.bat após mudanças.
- Regras invioláveis: nenhum dado de paciente no repo público; nunca varrer a pasta
  real de receitas; commits atômicos pt-BR.
