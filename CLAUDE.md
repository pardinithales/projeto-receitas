# CLAUDE.md

Leia e siga **AGENTS.md** (regras de privacidade LGPD, decisões de arquitetura e
convenções — é a fonte da verdade deste repositório) e **docs/CHECKPOINT.md**
(estado atual e próximos passos, atualizado a cada sessão).

Resumo mínimo:

- Sistema local de documentos médicos (FastAPI + SQLite) de consultório de neurologia.
- **Nenhum dado real de paciente entra no git** (repo público). Testes só com nomes fictícios.
- Nunca varrer a pasta real de receitas (`M:\...\Receitas Thales Pardini - Neurologia`).
- Nunca enviar nome de paciente para APIs de IA.
- Commits atômicos, em português. Rodar `python -m pytest tests/ -q` antes de commitar.
- Servidor sem auto-reload: o usuário precisa reiniciar `INICIAR-RECEITAS.bat` após mudanças.
