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
