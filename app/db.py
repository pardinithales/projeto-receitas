"""Banco SQLite: schema, conexão e carga do catálogo de medicamentos."""
import json
import shutil
import sqlite3
from datetime import date, datetime

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS pacientes (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    data_nascimento TEXT,
    cpf TEXT,
    cns TEXT,
    rg TEXT,
    nome_mae TEXT,
    peso_kg REAL,
    altura_cm REAL,
    telefone TEXT,
    endereco TEXT,
    cidade TEXT,
    uf TEXT,
    raca_cor TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS medicamentos (
    id INTEGER PRIMARY KEY,
    principio_ativo TEXT NOT NULL UNIQUE,
    grupo TEXT,
    classificacao_receita TEXT NOT NULL DEFAULT 'C1',
    disponibilidade TEXT NOT NULL DEFAULT '[]',
    lme INTEGER NOT NULL DEFAULT 0,
    obs TEXT
);

CREATE TABLE IF NOT EXISTS apresentacoes (
    id INTEGER PRIMARY KEY,
    medicamento_id INTEGER NOT NULL REFERENCES medicamentos(id) ON DELETE CASCADE,
    dose TEXT NOT NULL,
    forma TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posologias (
    id INTEGER PRIMARY KEY,
    apresentacao_id INTEGER NOT NULL REFERENCES apresentacoes(id) ON DELETE CASCADE,
    texto TEXT NOT NULL,
    qtd_30dias TEXT
);

CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY,
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
    tipo TEXT NOT NULL,               -- receita_controle_especial | receita_comum | lme | ...
    data_emissao TEXT NOT NULL,
    conteudo_json TEXT NOT NULL,      -- payload estruturado usado na geração (permite repetir/renovar)
    caminho_pdf TEXT
);

CREATE TABLE IF NOT EXISTS lme_dados (
    id INTEGER PRIMARY KEY,
    paciente_id INTEGER NOT NULL UNIQUE REFERENCES pacientes(id),
    cid10 TEXT,
    diagnostico TEXT,
    anamnese TEXT,
    tratamentos_previos TEXT,
    incapaz INTEGER NOT NULL DEFAULT 0,
    nome_responsavel TEXT,
    atualizado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documentos_paciente ON documentos(paciente_id, data_emissao DESC);
"""


def conectar() -> sqlite3.Connection:
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DATABASE_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def iniciar_banco() -> None:
    con = conectar()
    try:
        con.executescript(SCHEMA)
        _migrar(con)
        if con.execute("SELECT COUNT(*) FROM medicamentos").fetchone()[0] == 0:
            carregar_seed_medicamentos(con)
        con.commit()
    finally:
        con.close()


def _migrar(con: sqlite3.Connection) -> None:
    """Migrações aditivas para bancos criados em versões anteriores."""
    colunas = {r["name"] for r in con.execute("PRAGMA table_info(pacientes)")}
    if "tags" not in colunas:
        con.execute("ALTER TABLE pacientes ADD COLUMN tags TEXT")


def carregar_seed_medicamentos(con: sqlite3.Connection) -> int:
    seed = json.loads((config.SEEDS_DIR / "medicamentos.json").read_text(encoding="utf-8"))
    n = 0
    for med in seed["medicamentos"]:
        cur = con.execute(
            "INSERT OR IGNORE INTO medicamentos "
            "(principio_ativo, grupo, classificacao_receita, disponibilidade, lme, obs) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                med["principio_ativo"],
                med.get("grupo"),
                med.get("classificacao_receita", "C1"),
                json.dumps(med.get("disponibilidade", []), ensure_ascii=False),
                1 if med.get("lme") else 0,
                med.get("obs"),
            ),
        )
        if cur.rowcount == 0:
            continue
        med_id = cur.lastrowid
        for apr in med.get("apresentacoes", []):
            cur2 = con.execute(
                "INSERT INTO apresentacoes (medicamento_id, dose, forma) VALUES (?, ?, ?)",
                (med_id, apr["dose"], apr["forma"]),
            )
            apr_id = cur2.lastrowid
            for pos in apr.get("posologias", []):
                con.execute(
                    "INSERT INTO posologias (apresentacao_id, texto, qtd_30dias) VALUES (?, ?, ?)",
                    (apr_id, pos["texto"], pos.get("qtd_30dias")),
                )
        n += 1
    return n


def backup_banco() -> str | None:
    """Copia diária do banco (uma por dia; mantém as últimas 30)."""
    if not config.DATABASE_PATH.exists():
        return None
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destino = config.BACKUP_DIR / f"receitas-{date.today().isoformat()}.db"
    if not destino.exists():
        shutil.copy2(config.DATABASE_PATH, destino)
        antigos = sorted(config.BACKUP_DIR.glob("receitas-*.db"))[:-30]
        for velho in antigos:
            velho.unlink()
    return str(destino)


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")
