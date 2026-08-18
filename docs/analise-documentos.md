# Análise do fluxo atual de documentos

Levantamento feito por amostragem aleatória e direcionada (~32 arquivos de ~4.100)
da pasta de receitas do consultório. Nenhum dado real de paciente consta neste documento.

## Como funciona hoje

- Um arquivo `.docx` (ou PDF) por documento emitido, salvo em pasta única com subpastas
  por paciente (parcial) e uma pasta `MODELOS` com arquivos-base que são copiados e editados.
- O "banco de dados" é o nome do arquivo: `NOME DO PACIENTE medicamento dose diagnóstico tipo.docx`.
- Documentos são assinados digitalmente (ICP-Brasil) em parte dos casos; outros impressos/assinados à mão.

## Tipos de documento identificados

### 1. Receituário de Controle Especial (o mais frequente)
Estrutura fixa:

```
RECEITUÁRIO CONTROLE ESPECIAL
IDENTIFICAÇÃO DO EMITENTE            1ª VIA FARMÁCIA / 2ª VIA PACIENTE
Dr. <médico>  — CREMESP <nº>
Paciente: <nome>
USO ORAL (ou: USO ENDOVENOSO, em BIC)
<MEDICAMENTO> <dose> – <forma> ______________ <quantidade | USO CONTÍNUO>
    <posologia em linguagem natural, às vezes com observações longas>
[bloco IDENTIFICAÇÃO DO COMPRADOR / FORNECEDOR]
Assinatura: Dr. <médico> — Médico Neurologista — CRM-SP <nº> | RQE <nº>
```

Variações observadas:
- 1 a 3+ medicamentos por receita;
- quantidade em comprimidos/cápsulas/frascos OU "USO CONTÍNUO";
- posologias com horários específicos (ex.: parkinsonianos), frações (1 + ½),
  gotas, mL de solução oral, esquemas de titulação e observações de segurança
  ("não usar junto com X", "aumentar após 30 dias se tolerar");
- existe também variante "RECEITUÁRIO MÉDICO" (receita comum, não controlada).

### 2. LME — Laudo para Solicitação de Medicamento Especializado (CEAF/SUS)
- PDF oficial com campos AcroForm preenchíveis (confirmado: os dados ficam nos campos
  do formulário — é viável preencher programaticamente).
- Campos: CNES, estabelecimento, paciente, nome da mãe, peso, altura, até 6 medicamentos
  com quantidades para 6 meses, CID-10, diagnóstico, anamnese, tratamento prévio,
  atestado de capacidade, dados do médico, raça/cor, contatos.
- Acompanha frequentemente: "capa" com orientações da farmácia estadual (ex.: Farmácia de
  Minas), formulário estadual específico por doença (ex.: epilepsia MG), receita e relatório.
- Usado para alto custo: levetiracetam, lamotrigina, topiramato, gabapentina, clobazam,
  piridostigmina, azatioprina, imunoglobulina, donepezila, memantina, toxina botulínica etc.

### 3. Relatório médico
- Texto clínico livre com cabeçalho e assinatura padrão; inclui história, exame
  neurológico detalhado (força MRC por grupo muscular, reflexos, marcha), exames
  complementares, conclusão e CID-10. Cidade e data no rodapé (Barretos, <data>).
- Subtipos: relatório para farmácia de alto custo, relatório INSS, relatório de alta,
  relatório para toxina botulínica.

### 4. Encaminhamento
- Carta curta a outra especialidade (endocrino, fisioterapia, TO, neurocirurgia,
  vídeo-EEG...) com resumo do caso, justificativa e exames relevantes.

### 5. Atestado médico
- Texto padrão: compareceu em <data>, afastamento por <n> dias, CID-10 com
  autorização do paciente.

### 6. Outros
- Solicitações de exame (EEG, vídeo-EEG), escalas impressas (LANSS...), termos,
  orientações de uso de medicações para o paciente.

## Perfil de prescrição (frequência aproximada por nome de arquivo)

- Toxina botulínica/botox: ~290 arquivos
- Topiramato: ~195 | Donepezila/memantina/rivastigmina: ~141 | Valproato: ~115
- Clobazam: ~90 | Levodopa/pramipexol: ~84 | Carbamazepina: ~70
- Pregabalina: ~34 | Miastenia (piridostigmina): ~34 | Imunoglobulina: ~21
- Fenobarbital: ~21 | Lacosamida: ~9 | Clonazepam: ~8 | Esclerose múltipla: ~23

Perfil: neurologia geral com ênfase em epilepsia (inclusive neuro-oncologia),
cefaleia/migrânea crônica, demência, Parkinson, dor neuropática, neuromuscular
(miastenia, Guillain-Barré) e toxina botulínica.

## Dores do fluxo atual

1. Repetição manual: copiar modelo, trocar nome, medicação, posologia — a cada consulta.
2. Nenhuma estrutura de dados: histórico do paciente espalhado em nomes de arquivo.
3. LME re-preenchido à mão a cada renovação (a cada 6 meses) com os mesmos dados.
4. Risco de erro: nome de paciente errado dentro do arquivo (observado em amostra:
   arquivo com nome de um paciente e conteúdo de outro — herança da cópia de modelo).
5. Sem padronização de posologia/apresentação por medicamento.
