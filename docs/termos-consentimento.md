# Termos de consentimento (TER/TCLE) e anexos por medicamento

Fonte: pasta local `M:\Thales Pardini - Neurologia\TERMOS DE CONSENTIMENTO`
(PDFs originais ficam fora do repo até serem sanitizados/recriados).

## Inventário atual

| Arquivo (local) | Cobre | Observação |
|---|---|---|
| TERMO_EPILEPSIA ... LEVETIRACETAM ... MARCAVEL.pdf | TER único de anticonvulsivantes CEAF: ácido valproico, carbamazepina, clobazam, clonazepam, etossuximida, fenitoína, fenobarbital, gabapentina, lamotrigina, levetiracetam, primidona, topiramato, vigabatrina | Já é "marcável" (campos) |
| TCLE piridostigmina mestinom azatioprina.pdf | Miastenia | |
| TCLE GUILLAIN BARRE IVIG.pdf | Imunoglobulina EV | |
| TERMO CONSENTIMENTO GABAPENTINA DOR CRONICA.pdf | Gabapentina para dor | |
| ESCALA_evas_lanss_dor_gabapentina.pdf | Escalas EVA + LANSS | Anexo obrigatório do LME de gabapentina; padrão do consultório: LANSS 21 pts, EVA 8 (pré-preencher, permitir ajuste) |
| TCLE BOTOX TOXINA BOTULINICA.pdf | Toxina botulínica | |
| termo_lme_donepezila_galantamina_rivastigmina ... .pdf | Anticolinesterásicos/demência | Inclui CDR e Mini-Mental (MEEM) |
| MODELO PEDIDOS EXAME AZATIOPRINA.docx | Exames de monitorização de azatioprina | |

## Plano (v1/v2)

- Recriar cada termo como **formulário preenchível pelo sistema** (mesmo texto, layout fiel),
  com campos: nome do paciente, medicamentos marcados, data, cidade.
- O gerador de kit LME (ver `docs/lme-campos.md`) anexa automaticamente o termo certo
  conforme o medicamento selecionado.
- Escalas (EVA/LANSS, MEEM/CDR) entram pré-preenchidas com os valores-padrão definidos
  pelo usuário, sempre editáveis antes de gerar o PDF final.
