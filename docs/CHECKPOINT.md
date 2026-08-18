# CHECKPOINT — estado do projeto (atualizado em 18/08/2026, fim do dia)

Leia junto com `AGENTS.md`. 33 testes passando.

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

1. Validar na prática o kit LME impresso (usuário estava testando; reiniciar o .bat
   carrega as correções do med1/dropdowns/carimbo).
2. TERs restantes preenchíveis (hoje só epilepsia é preenchido; os outros são copiados).
3. Escalas como folhas preenchidas (MEEM/CDR/EDSS/LANSS impressos com respostas
   marcadas) — fonte: pasta "Escalas e ferramentas uteis" (protocolo USP) e
   ESCALA_evas_lanss (LANSS 21, EVA 8 padrão).
4. Formulários estaduais MG/GO (flat PDFs — precisam overlay ou recriação).
5. Baixar fichas SES-SP dos demais fármacos (demência, EM, toxina, pramipexol...).

## Avisos

- Servidor sem auto-reload: fechar e reabrir INICIAR-RECEITAS.bat após mudanças.
- Regras invioláveis: nenhum dado de paciente no repo público; nunca varrer a pasta
  real de receitas; commits atômicos pt-BR.
