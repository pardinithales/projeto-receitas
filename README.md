# projeto-receitas

Sistema eletrônico local para geração de documentos médicos de um consultório de neurologia:
receituários de controle especial, receitas de uso contínuo, LMEs (Laudo para Solicitação de
Medicamento Especializado / CEAF-SUS), relatórios médicos, encaminhamentos e atestados.

## Objetivo

Substituir o fluxo atual (copiar/editar arquivos .docx soltos, um por paciente) por um sistema
com banco de dados local (SQLite) que:

- cadastra pacientes uma única vez (nome, documentos, dados para LME);
- mantém catálogo de medicamentos com apresentações e posologias mais usadas;
- gera os documentos prontos (docx/PDF) a partir de modelos fixos;
- guarda histórico de tudo que foi emitido por paciente;
- preenche programaticamente os PDFs oficiais de LME (AcroForm) e formulários estaduais.

## Privacidade (regra inegociável)

**Nenhum dado de paciente entra neste repositório.** O banco de dados, documentos gerados e
qualquer arquivo real ficam apenas na máquina local, protegidos pelo `.gitignore`.
Commits contêm somente código, modelos sanitizados (nomes fictícios) e documentação.

## Como rodar

```
pip install -r requirements.txt
copy .env.example .env      # e preencher com os dados do prescritor
python -m uvicorn app.main:app --port 8477
```

Abrir http://localhost:8477 no navegador. O banco SQLite é criado e populado
com o catálogo de medicamentos automaticamente no primeiro uso; um backup
diário é feito a cada inicialização.

Scripts locais (não movem nenhum dado para o repositório):

- `python scripts/importar_pacientes_lme.py 10` — importa pacientes reais dos LMEs recentes;
- `python scripts/validar_com_receitas_reais.py 20` — confere que o PDF gerado
  reproduz fielmente receitas antigas.

## Status

v1 funcional para receitas (controle especial e comum). Próximo: kit LME
(PDF oficial preenchido + formulário estadual + termos + escalas). Ver `AGENTS.md`.
