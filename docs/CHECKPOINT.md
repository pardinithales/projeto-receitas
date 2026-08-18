# CHECKPOINT — estado do projeto (atualizado em 18/08/2026)

Leia junto com `AGENTS.md` (regras e decisões) antes de retomar o trabalho.

## O que está PRONTO e funcionando (v1 — receitas)

| Área | Estado |
|---|---|
| Repositório | github.com/pardinithales/projeto-receitas, branch `main`, tudo pushado |
| Inicialização | `INICIAR-RECEITAS.bat` (duplo clique → instala deps, sobe servidor, abre navegador em http://localhost:8477) |
| Banco | SQLite em `dados/receitas.db` (drive M:, fora do git), criado/populado no 1º uso, backup diário automático |
| Catálogo | 48 fármacos, 91 apresentações, 125 posologias (seed em `seeds/medicamentos.json`) |
| Pacientes | Cadastro mínimo (só nome obrigatório); 10 pacientes reais já importados dos LMEs com mãe/peso/altura/CID/anamnese |
| Receita | Tela toda por seleção: autocomplete, chips de posologia, quantidade automática, avisos B1/alto custo, COM/SEM data (sem data = papel sem campo de data), controle especial e comum, USO ORAL/EV etc. |
| Salvamento | Toda receita emitida fica no histórico; botão "Deixar salvo (gerar depois)" grava sem abrir PDF (gera na 1ª abertura); "repetir" em 1 clique |
| PDF | reportlab sobre papel timbrado local (`templates/assets/`, fora do git); validado contra 20/20 receitas reais |
| Testes | 11 pytest passando (`python -m pytest tests/ -q`) — só dados fictícios |
| Scripts locais | `scripts/importar_pacientes_lme.py N` e `scripts/validar_com_receitas_reais.py N` |

## PRÓXIMO MARCO: kit LME (ainda não iniciado)

Gerar de uma vez, por medicamento de alto custo:
1. **LME oficial preenchido** — PDF AcroForm; mapa de campos pronto em `docs/lme-campos.md`;
   usar pikepdf (latin-1, xref corrompida); template em branco deve ser criado limpando
   os campos de um exemplar real (NUNCA commitar exemplar preenchido);
   atenção ao dropdown `Selecao med 1` que fica com "Lovastatina" residual.
2. Receita do medicamento (já existe o gerador).
3. Relatório para farmácia de alto custo (modelo em docs/analise-documentos.md).
4. Formulário estadual (ex.: epilepsia-MG) conforme estado do paciente.
5. Termo TER/TCLE do grupo (inventário em `docs/termos-consentimento.md`).
6. Anexos por medicamento: gabapentina → EVA+LANSS pré-preenchidas (LANSS 21 pts, EVA 8);
   donepezila/rivastigmina/galantamina → termo com CDR e MEEM.

Dados por paciente já existem na tabela `lme_dados` (cid10, diagnóstico, anamnese,
tratamentos prévios) — os 10 importados já vieram preenchidos.
Constantes (CNES, estabelecimento, CNS do médico) estão no `.env` local.

## Backlog depois do LME

- Relatórios médicos, encaminhamentos, atestados (modelos em docs/analise-documentos.md).
- Recriar TCLEs como formulários preenchíveis.
- Edição de paciente e de dados de LME pela interface (hoje só criação).
- Renovação semestral de LME em 1 clique a partir de `lme_dados` + último kit.

## Avisos operacionais

- Servidor não tem auto-reload: após atualizar o código, fechar e reabrir o `.bat`.
- Regras invioláveis: nenhum dado de paciente no repo (público); nunca varrer a pasta
  real de receitas inteira; commits atômicos em pt-BR.
