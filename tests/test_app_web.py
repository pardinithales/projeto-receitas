"""Teste ponta-a-ponta do app web com banco temporário — dados fictícios."""
import json

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "teste.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "documentos")
    db.iniciar_banco()
    return TestClient(app)


def test_fluxo_completo_receita(cliente):
    r = cliente.post("/pacientes", data={"nome": "Maria Exemplo da Silva"},
                     follow_redirects=False)
    assert r.status_code == 303
    pid = r.headers["location"].rsplit("/", 1)[-1]

    itens = [{"medicamento": "Levetiracetam 250mg - comprimido",
              "quantidade": "120 comprimidos",
              "posologia": "Tomar 2 comprimidos de 12 em 12 horas"}]
    r = cliente.post(f"/pacientes/{pid}/receita", data={
        "tipo": "controle_especial", "via_administracao": "USO ORAL",
        "com_data": "sem", "itens_json": json.dumps(itens),
    }, follow_redirects=False)
    assert r.status_code == 303
    url_pdf = r.headers["location"]

    r = cliente.get(url_pdf)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"

    # histórico registrado e botão de repetir funcional
    r = cliente.get(f"/pacientes/{pid}")
    assert "Levetiracetam" in r.text
    r = cliente.get(f"/pacientes/{pid}/receita?copiar_de=1")
    assert "Tomar 2 comprimidos" in r.text


def test_busca_paciente(cliente):
    cliente.post("/pacientes", data={"nome": "Joana Exemplo Teste"})
    r = cliente.get("/pacientes/busca", params={"q": "joana"})
    assert "Joana Exemplo Teste" in r.text


def test_catalogo_tem_estruturas(cliente):
    cat = cliente.get("/api/catalogo").json()
    lev = next(m for m in cat if m["principio_ativo"] == "Levetiracetam")
    assert lev["lme"] is True
    assert lev["apresentacoes"][0]["posologias"]
