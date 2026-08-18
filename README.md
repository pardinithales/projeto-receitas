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

## Status

Em levantamento de requisitos — ver `AGENTS.md` (em construção) e `docs/`.
