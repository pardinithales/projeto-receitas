# AGENTS.md — projeto-receitas

Guia para agentes (Claude Code e afins) trabalhando neste repositório.

## O que é este projeto

Sistema eletrônico **local** para o consultório de neurologia do Dr. Thales Pardini Fagundes
(Barretos-SP) gerar documentos médicos que hoje são feitos copiando/editando arquivos .docx:
receituários, LMEs, relatórios, encaminhamentos e atestados.
Análise detalhada do fluxo atual: `docs/analise-documentos.md`.

## Regras inegociáveis de privacidade (LGPD)

1. **Nenhum dado real de paciente entra no repositório** — nem em código, commit, teste,
   fixture, exemplo, mensagem de commit ou documentação. O repositório no GitHub é público.
2. Nomes em testes/exemplos/seeds são **sempre fictícios** (ex.: "Maria Exemplo da Silva").
3. Banco de dados, PDFs gerados e backups ficam fora do git (ver `.gitignore` — não afrouxar).
4. A pasta real de receitas (`M:\Thales Pardini - Neurologia\Receitas Thales Pardini - Neurologia`,
   ~4.100 arquivos) **nunca deve ser varrida por completo**: acesso somente por amostragem
   pequena e direcionada, quando explicitamente necessário.
5. Dados do médico (nome, CRM, RQE) são públicos e podem aparecer em templates.

## Decisões de arquitetura (fechadas com o usuário)

| Tema | Decisão |
|---|---|
| Interface | App web local: FastAPI + Jinja2 + HTMX, aberto no navegador |
| Banco | SQLite, arquivo no drive `M:` (rede do consultório), com backup automático |
| Escopo v1 | Receituário de controle especial, receita comum/uso contínuo e LME (PDF oficial AcroForm preenchido) + formulários estaduais |
| v2+ | Relatórios, encaminhamentos, atestados, solicitações de exame |
| Saída | **PDF pronto para imprimir** (assinatura à mão no consultório) |
| Pacientes | Cadastro começa vazio; paciente é cadastrado no primeiro uso |
| Medicamentos | Catálogo curado de neurologia **pré-carregado** (seed versionado no git) |
| Prescritor | Fixo: Dr. Thales Pardini Fagundes, CRM-SP 220298, RQE 124154; estabelecimento/CNES único (valores em `.env` local, modelo em `.env.example`) |
| Papel timbrado | Imagem institucional (Hospital de Amor Barretos) em `templates/assets/` — **local apenas, fora do git** (repo é público) |
| Kit LME | O LME nunca sai sozinho: LME preenchido + receita com posologia + termo TER pelo CID + relatório alto custo opcional — ver `docs/lme-campos.md` e `docs/termos-consentimento.md` |
| CIDs | Cada medicamento carrega seus CIDs contemplados (campo `cids` do seed); indicação única auto-preenche (epilepsia G40.1, Alzheimer G30.1), múltipla pergunta; o CID dispara escalas/termo/validações |
| Escalas | MEEM/CDR/escolaridade (G30/F00), EDSS (G35), LANSS/EVA com padrão 21/8 (R52) — obrigatórias pelo PCDT, salvas na tabela `escalas`, injetadas na anamnese |
| Carimbo | Imagem transparente local (`templates/assets/carimbo.png`); senha `CARIMBO_SENHA` (+ mestra) no `.env`, liberação de 24h; aplicado como conteúdo de página |
| Impressão | SumatraPDF portátil em `tools/` (fora do git); fila com retomada em `/impressao`; impressora salva na tabela `config` |
| IA | OpenAI: GPT-5.6 Sol (relatórios INSS/alto custo/anamnese, prompts-base = .txt do usuário em Prompts principais) e gpt-5.6-luna (extração de diagnósticos p/ tags). **Nunca enviar nome de paciente à API** — identificação só no PDF local |
| Sistema leve | PDFs > 7 dias apagados; TODO documento é regenerável do `conteudo_json` (`_regenerar_pdf`); não guardar docx/pdf permanentes |
| Backups | Diário em `dados/backups` (30 cópias) + mensal em `M:\...\backup-sistema` |

## Princípio central de UX: marcar, não digitar

O usuário atende em consultório com tempo curto. Toda a interface deve ser de
**seleção**: autocomplete, botões, checkboxes, posologias sugeridas por medicamento,
quantidades calculadas automaticamente (posologia × dias), "repetir última receita"
em um clique, renovação de LME reaproveitando os dados anteriores.
Texto livre é exceção, aceitável apenas em campos tipo anamnese/observações —
e mesmo ali com frases-modelo selecionáveis.

## Modelo de dados (orientação inicial)

- `pacientes` — nome, data de nascimento, CPF/CNS, RG, nome da mãe, peso, altura,
  telefone, endereço, raça/cor (campos exigidos pelo LME).
- `medicamentos` — princípio ativo, apresentações (dose + forma farmacêutica),
  classificação de receita (comum, controle especial C1, notificação B/azul),
  disponibilidade (REMUME / CEAF alto custo / farmácia comum), posologias-padrão.
- `documentos` — tudo que foi emitido: paciente, tipo, data, conteúdo estruturado
  (JSON), caminho do PDF gerado. É o histórico que alimenta sugestões e renovações.
- `lme_dados` — por paciente: CID-10, diagnóstico, anamnese-base, tratamentos prévios,
  medicamentos com quantidades por 6 meses (renovação semestral quase idêntica).

## Domínio (glossário mínimo)

- **Receituário de Controle Especial**: receita branca em 2 vias (farmácia/paciente) com
  blocos de identificação do comprador e fornecedor. Usada para anticonvulsivantes,
  antidepressivos etc. (Portaria 344/98, lista C1).
- **LME**: Laudo para Solicitação, Avaliação e Autorização de Medicamentos do
  Componente Especializado (CEAF/SUS). PDF oficial com campos AcroForm. Renovado a cada
  6 meses. Vem acompanhado de receita, relatório e formulário estadual específico
  (ex.: epilepsia-MG). Pacientes de SP e MG.
- **REMUME**: medicamentos da farmácia municipal básica (carbamazepina, valproato,
  fenobarbital, fenitoína...). Receita de controle especial comum resolve.
- **Alto custo (CEAF)**: levetiracetam, lamotrigina, topiramato, clobazam, lacosamida,
  donepezila, memantina, piridostigmina, azatioprina, imunoglobulina, toxina botulínica,
  medicações de esclerose múltipla... exigem LME.
- Posologias reais incluem: frações (1 + ½ comprimido), gotas, mL de solução oral,
  horários fixos (parkinsonianos), esquemas de titulação e infusão EV em BIC
  (imunoglobulina). O modelo de posologia precisa suportar isso.

## Stack e convenções técnicas

- Python 3.13. Dependências geridas em `requirements.txt` (ou `pyproject.toml`).
- PDF dos documentos de texto: gerar com **reportlab** (layout determinístico, fiel aos
  modelos em `docs/analise-documentos.md`).
- LME e formulários oficiais: preencher AcroForm com **pikepdf/pypdf** — atenção:
  os PDFs oficiais usam encoding latin-1 nos valores; tratar explicitamente.
- Modelos oficiais em branco (LME, formulários estaduais) ficam em `templates/` —
  única exceção de PDF permitida no git (são formulários públicos do SUS).
- Testes com `pytest`; fixtures só com dados fictícios.
- Código, comentários, UI e commits em **português brasileiro**.

## Convenções de git

- Commits **atômicos** (uma mudança lógica por commit), no formato conventional commits
  em pt-BR: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- Antes de todo commit: conferir que nenhum arquivo com dado real entrou no stage
  (`git status` + revisar diff). Na dúvida, não commitar.
- Remote: `https://github.com/pardinithales/projeto-receitas.git` (público).

## Estrutura de pastas prevista

```
sistema-receita/
├── AGENTS.md
├── README.md
├── docs/                  # análises e decisões (sanitizadas)
├── templates/             # formulários oficiais em branco (LME etc.) + modelos de layout
├── app/                   # FastAPI: rotas, modelos, serviços, geração de PDF
│   ├── main.py
│   ├── db.py              # SQLite; caminho do banco configurável via .env (fora do git)
│   ├── models/
│   ├── services/          # geração de receita, preenchimento de LME, backup
│   └── templates/         # Jinja2 (telas)
├── seeds/                 # catálogo curado de medicamentos (JSON/YAML versionado)
└── tests/
```
