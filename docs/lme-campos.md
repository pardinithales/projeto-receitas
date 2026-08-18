# LME — mapa de campos do PDF oficial (AcroForm)

O LME do CEAF é um PDF com campos de formulário preenchíveis. Nomes dos campos
extraídos de um exemplar real (valores omitidos — dados de paciente nunca entram no repo):

| Campo AcroForm | Conteúdo |
|---|---|
| `CNES` | Número do CNES do estabelecimento |
| `Nome do estabelecimento de saúde` | Ex.: `02 - HA ANTENOR DUARTE VILELA` |
| `Nome do paciente` | Nome completo |
| `Nome da mãe do paciente` | Nome da mãe |
| `Peso` / `Altura` | kg / cm |
| `med1`, `med2`, ... | Medicamento por extenso: `Levetiracetam 750mg - comprimido` |
| `Selecao med 1`, ... | Dropdown de seleção de medicamento (atenção: pode ficar com valor default incoerente, ex. "Lovastatina 40 mg" — conferir/limpar ao preencher) |
| `Text6`–`Text8`, `Text6a`–`Text8a` | Quantidades mês 1–6 do medicamento 1 |
| `Text10`–`Text12`, `Text10a`–`Text12a` | Quantidades mês 1–6 do medicamento 2 |
| `CID` | CID-10 (ex.: G40.1) |
| `Diagnóstico` | Texto do diagnóstico |
| `Anamnese` | Anamnese resumida |
| `tratamentos prévios` | Tratamentos anteriores |
| `Nome do Responsável` | Responsável (atestado de capacidade) |
| `Text46` | Nome do médico solicitante |
| `TextCNS` | CNS do médico solicitante |
| `Today` | Data da solicitação (dd/mm/aaaa) |

Observações técnicas:

- Valores dos campos usam encoding **latin-1** em parte dos exemplares; tratar na leitura/escrita.
- Alguns PDFs têm xref corrompida ("wrong pointing object") — usar parser tolerante (pikepdf).
- O template em branco para o sistema deve ser obtido **limpando os campos** de um exemplar,
  nunca commitando exemplar real.

## Constantes do prescritor (valores reais só em `.env` local)

- CNES: ver `.env` (`LME_CNES`) — atenção: já houve exemplar antigo com CNES digitado
  errado (dígito faltando), motivação direta para o preenchimento automático.
- Estabelecimento: `.env` (`LME_ESTABELECIMENTO`)
- Nome do médico / CNS do médico: `.env` (`MEDICO_NOME`, `MEDICO_CNS`)

## Documentos que acompanham o LME (kit por medicamento)

O sistema deve gerar o **kit completo** de uma vez:

1. LME preenchido (PDF oficial);
2. Receita do medicamento (controle especial);
3. Relatório médico para farmácia de alto custo (quando aplicável);
4. Formulário estadual específico da doença (ex.: epilepsia-MG), conforme estado do paciente;
5. Capa de orientações da farmácia estadual (MG), quando aplicável;
6. Termo de esclarecimento e responsabilidade (TER/TCLE) do grupo de medicamentos;
7. Anexos exigidos por medicamento específico — regras conhecidas:
   - **Gabapentina (dor crônica/neuropática)**: exige escalas **EVA e LANSS** preenchidas.
     Padrão usual do consultório: LANSS 21 pontos, EVA 8 — pré-preencher e permitir ajuste.
     Modelo: pasta `TERMOS DE CONSENTIMENTO` (`ESCALA_evas_lanss_dor_gabapentina.pdf`).
   - **Donepezila/galantamina/rivastigmina (demência)**: termo próprio com CDR e
     Mini-Mental (MEEM) — campos de escala no termo.
   - **Epilepsia**: diário de crises (renovações) + laudo de EEG/imagem na solicitação inicial.
