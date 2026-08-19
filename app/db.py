"""Banco SQLite: schema, conexão e carga do catálogo de medicamentos."""
import json
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

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

CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS impressao_fila (
    id INTEGER PRIMARY KEY,
    documento_id INTEGER REFERENCES documentos(id),
    caminho TEXT NOT NULL,
    descricao TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',   -- pendente | ok | erro
    erro TEXT,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escalas (
    id INTEGER PRIMARY KEY,
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
    tipo TEXT NOT NULL,               -- MEEM | CDR | EDSS | EVA | LANSS
    valor TEXT NOT NULL,
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documentos_paciente ON documentos(paciente_id, data_emissao DESC);
CREATE INDEX IF NOT EXISTS idx_escalas_paciente ON escalas(paciente_id, tipo, data DESC);
"""


def _sem_acento(texto: str | None) -> str:
    """Busca tolerante: 'jose' acha 'José' (e vice-versa)."""
    import unicodedata
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def conectar() -> sqlite3.Connection:
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DATABASE_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.create_function("sem_acento", 1, _sem_acento, deterministic=True)
    return con


def iniciar_banco() -> None:
    con = conectar()
    try:
        con.executescript(SCHEMA)
        _migrar(con)
        sincronizar_seed_medicamentos(con)
        con.commit()
    finally:
        con.close()


def _migrar(con: sqlite3.Connection) -> None:
    """Migrações aditivas para bancos criados em versões anteriores."""
    colunas = {r["name"] for r in con.execute("PRAGMA table_info(pacientes)")}
    if "tags" not in colunas:
        con.execute("ALTER TABLE pacientes ADD COLUMN tags TEXT")
    if "escolaridade_anos" not in colunas:
        con.execute("ALTER TABLE pacientes ADD COLUMN escolaridade_anos REAL")
    colunas_med = {r["name"] for r in con.execute("PRAGMA table_info(medicamentos)")}
    if "cids" not in colunas_med:
        con.execute("ALTER TABLE medicamentos ADD COLUMN cids TEXT")


def sincronizar_seed_medicamentos(con: sqlite3.Connection) -> None:
    """Upsert idempotente do catálogo: novos fármacos/apresentações/posologias do seed
    entram em bancos já existentes; edições manuais no banco não são apagadas."""
    seed = json.loads((config.SEEDS_DIR / "medicamentos.json").read_text(encoding="utf-8"))
    for med in seed["medicamentos"]:
        row = con.execute("SELECT id FROM medicamentos WHERE principio_ativo = ?",
                          (med["principio_ativo"],)).fetchone()
        cids_json = json.dumps(med.get("cids", []), ensure_ascii=False)
        if row:
            med_id = row["id"]
            con.execute("UPDATE medicamentos SET grupo = ?, classificacao_receita = ?, "
                        "disponibilidade = ?, lme = ?, obs = ?, cids = ? WHERE id = ?",
                        (med.get("grupo"), med.get("classificacao_receita", "C1"),
                         json.dumps(med.get("disponibilidade", []), ensure_ascii=False),
                         1 if med.get("lme") else 0, med.get("obs"), cids_json, med_id))
        else:
            med_id = con.execute(
                "INSERT INTO medicamentos "
                "(principio_ativo, grupo, classificacao_receita, disponibilidade, lme, "
                "obs, cids) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (med["principio_ativo"], med.get("grupo"),
                 med.get("classificacao_receita", "C1"),
                 json.dumps(med.get("disponibilidade", []), ensure_ascii=False),
                 1 if med.get("lme") else 0, med.get("obs"), cids_json),
            ).lastrowid
        for apr in med.get("apresentacoes", []):
            arow = con.execute(
                "SELECT id FROM apresentacoes WHERE medicamento_id = ? AND dose = ? "
                "AND forma = ?", (med_id, apr["dose"], apr["forma"])).fetchone()
            apr_id = arow["id"] if arow else con.execute(
                "INSERT INTO apresentacoes (medicamento_id, dose, forma) VALUES (?, ?, ?)",
                (med_id, apr["dose"], apr["forma"])).lastrowid
            for pos in apr.get("posologias", []):
                existe = con.execute(
                    "SELECT 1 FROM posologias WHERE apresentacao_id = ? AND texto = ?",
                    (apr_id, pos["texto"])).fetchone()
                if not existe:
                    con.execute(
                        "INSERT INTO posologias (apresentacao_id, texto, qtd_30dias) "
                        "VALUES (?, ?, ?)",
                        (apr_id, pos["texto"], pos.get("qtd_30dias")))


def backup_banco() -> str | None:
    """Copia diária do banco (uma por dia; mantém as últimas 30) e cópia mensal
    em pasta separada do drive M: (backup-sistema)."""
    if not config.DATABASE_PATH.exists():
        return None
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destino = config.BACKUP_DIR / f"receitas-{date.today().isoformat()}.db"
    if not destino.exists():
        shutil.copy2(config.DATABASE_PATH, destino)
        antigos = sorted(config.BACKUP_DIR.glob("receitas-*.db"))[:-30]
        for velho in antigos:
            velho.unlink()
    try:
        mensal_dir = config.BACKUP_MENSAL_DIR
        mensal_dir.mkdir(parents=True, exist_ok=True)
        mensal = mensal_dir / f"receitas-{date.today():%Y-%m}.db"
        if not mensal.exists():
            shutil.copy2(config.DATABASE_PATH, mensal)
    except OSError:
        pass    # drive de rede indisponível não pode impedir o sistema de subir
    return str(destino)


def limpar_pdfs_antigos(dias: int = 7) -> int:
    """Apaga PDFs gerados com mais de N dias — tudo é regenerável a partir do
    banco (o conteúdo estruturado fica em documentos.conteudo_json)."""
    from datetime import datetime, timedelta
    limite = (datetime.now() - timedelta(days=dias)).timestamp()
    apagados = 0
    con = conectar()
    try:
        for doc in con.execute("SELECT id, caminho_pdf FROM documentos "
                               "WHERE caminho_pdf IS NOT NULL").fetchall():
            caminho = Path(doc["caminho_pdf"])
            try:
                if caminho.exists() and caminho.stat().st_mtime < limite:
                    caminho.unlink()
                    apagados += 1
                if not caminho.exists():
                    con.execute("UPDATE documentos SET caminho_pdf = NULL WHERE id = ?",
                                (doc["id"],))
            except OSError:
                continue
        con.commit()
    finally:
        con.close()
    return apagados


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")
