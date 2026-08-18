"""Estatísticas, exclusões, regeneração universal e limpeza de PDFs — fictício."""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "teste.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "BACKUP_MENSAL_DIR", tmp_path / "backup-sistema")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "documentos")
    db.iniciar_banco()
    return TestClient(app)


def _paciente_com_receita(cliente, nome="Estat Exemplo Um"):
    r = cliente.post("/pacientes", data={"nome": nome}, follow_redirects=False)
    pid = r.headers["location"].rsplit("/", 1)[-1]
    r = cliente.post(f"/pacientes/{pid}/receita", data={
        "tipo": "controle_especial", "via_administracao": "USO ORAL",
        "com_data": "sem", "acao": "gerar", "tags": "epilepsia focal, astrocitoma",
        "itens_json": json.dumps([{"medicamento": "Levetiracetam 750mg - comprimido",
                                   "quantidade": "60 comprimidos",
                                   "posologia": "Tomar 1 comprimido de 12/12h"}]),
    }, follow_redirects=False)
    return pid, int(r.headers["location"].split("/")[2])


def test_estatisticas_mostram_meds_e_tags(cliente):
    _paciente_com_receita(cliente)
    r = cliente.get("/estatisticas")
    assert "levetiracetam — 1 paciente" in r.text.lower()
    assert "astrocitoma" in r.text


def test_tags_salvas_pela_receita(cliente):
    pid, _ = _paciente_com_receita(cliente, "Estat Tags Dois")
    con = db.conectar()
    tags = con.execute("SELECT tags FROM pacientes WHERE id = ?", (pid,)).fetchone()[0]
    con.close()
    assert "astrocitoma" in tags


def test_limpeza_e_regeneracao_de_pdf(cliente):
    pid, doc_id = _paciente_com_receita(cliente, "Estat Regen Tres")
    con = db.conectar()
    caminho = Path(con.execute("SELECT caminho_pdf FROM documentos WHERE id = ?",
                               (doc_id,)).fetchone()["caminho_pdf"])
    con.close()
    # envelhece o arquivo e roda a limpeza
    velho = time.time() - 8 * 24 * 3600
    os.utime(caminho, (velho, velho))
    assert db.limpar_pdfs_antigos(dias=7) == 1
    assert not caminho.exists()
    # abrir de novo regenera na hora
    r = cliente.get(f"/documentos/{doc_id}/pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"


def test_excluir_documento_e_paciente(cliente):
    pid, doc_id = _paciente_com_receita(cliente, "Estat Excluir Quatro")
    r = cliente.post(f"/documentos/{doc_id}/excluir", follow_redirects=False)
    assert r.status_code == 303
    con = db.conectar()
    assert con.execute("SELECT COUNT(*) FROM documentos WHERE id = ?",
                       (doc_id,)).fetchone()[0] == 0
    con.close()
    r = cliente.post(f"/pacientes/{pid}/excluir", follow_redirects=False)
    assert r.status_code == 303
    con = db.conectar()
    assert con.execute("SELECT COUNT(*) FROM pacientes WHERE id = ?",
                       (pid,)).fetchone()[0] == 0
    con.close()


def test_backup_mensal_criado(cliente, tmp_path):
    db.backup_banco()
    assert list((tmp_path / "backup-sistema").glob("receitas-*.db"))
