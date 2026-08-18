"""Configuração do sistema — valores reais vêm do .env (nunca versionado)."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(RAIZ / "dados" / "receitas.db")))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(RAIZ / "dados" / "backups")))

MEDICO_NOME = os.getenv("MEDICO_NOME", "")
MEDICO_CRM = os.getenv("MEDICO_CRM", "")
MEDICO_RQE = os.getenv("MEDICO_RQE", "")
MEDICO_CNS = os.getenv("MEDICO_CNS", "")

LME_CNES = os.getenv("LME_CNES", "")
LME_ESTABELECIMENTO = os.getenv("LME_ESTABELECIMENTO", "")

CIDADE_PADRAO = os.getenv("CIDADE_PADRAO", "Barretos")

SEEDS_DIR = RAIZ / "seeds"
TEMPLATES_DIR = RAIZ / "templates"
PAPEL_TIMBRADO = TEMPLATES_DIR / "assets" / "papel-timbrado-ha-barretos.jpeg"
SAIDA_DIR = Path(os.getenv("SAIDA_DIR", str(RAIZ / "dados" / "documentos")))

# Carimbo digital (imagem local, fora do git) — aplicado só com a senha correta
CARIMBO_PATH = Path(os.getenv("CARIMBO_PATH",
                              str(TEMPLATES_DIR / "assets" / "carimbo.png")))
CARIMBO_SENHA = os.getenv("CARIMBO_SENHA", "carimbo")
CARIMBO_SENHA_MESTRA = os.getenv("CARIMBO_SENHA_MESTRA", "")   # fallback (ex.: telefone)
CARIMBO_DICA = os.getenv("CARIMBO_DICA", "")                   # pista mostrada no erro

# Impressão direta (SumatraPDF portátil, fora do git)
IMPRESSORA_PADRAO = os.getenv("IMPRESSORA_PADRAO", "HP 3015")
SUMATRA_PATH = Path(os.getenv("SUMATRA_PATH",
                              str(RAIZ / "tools" / "sumatra" / "SumatraPDF-3.5.2-64.exe")))
TERMOS_DIR = Path(os.getenv("TERMOS_DIR",
                            r"M:\Thales Pardini - Neurologia\TERMOS DE CONSENTIMENTO"))
