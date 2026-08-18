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


def test_emitir_sempre_salva_no_historico(cliente):
    """Após emitir (gerar PDF), a receita fica salva e reaproveitável."""
    r = cliente.post("/pacientes", data={"nome": "Carlos Exemplo Reuso"},
                     follow_redirects=False)
    pid = r.headers["location"].rsplit("/", 1)[-1]
    itens = [{"medicamento": "Topiramato 50mg - comprimido",
              "quantidade": "60 comprimidos",
              "posologia": "Tomar 1 comprimido de 12 em 12 horas"}]
    cliente.post(f"/pacientes/{pid}/receita", data={
        "tipo": "controle_especial", "via_administracao": "USO ORAL",
        "com_data": "sem", "acao": "gerar", "itens_json": json.dumps(itens)})
    pagina = cliente.get(f"/pacientes/{pid}").text
    assert "Topiramato" in pagina          # está no histórico
    assert "salva p/ depois" not in pagina  # e já tem PDF gerado


def test_deixar_salvo_gera_pdf_depois(cliente):
    r = cliente.post("/pacientes", data={"nome": "Ana Exemplo Salvar"},
                     follow_redirects=False)
    pid = r.headers["location"].rsplit("/", 1)[-1]
    itens = [{"medicamento": "Sertralina 50mg - comprimido",
              "quantidade": "90 comprimidos",
              "posologia": "Tomar 3 comprimidos pela manhã"}]
    r = cliente.post(f"/pacientes/{pid}/receita", data={
        "tipo": "controle_especial", "via_administracao": "USO ORAL",
        "com_data": "sem", "acao": "salvar", "itens_json": json.dumps(itens),
    }, follow_redirects=False)
    assert r.headers["location"] == f"/pacientes/{pid}"   # volta ao paciente, sem abrir PDF
    pagina = cliente.get(f"/pacientes/{pid}").text
    assert "salva p/ depois" in pagina
    # primeira abertura gera o PDF na hora
    doc_id = pagina.split("/documentos/")[1].split("/")[0]
    r = cliente.get(f"/documentos/{doc_id}/pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert "salva p/ depois" not in cliente.get(f"/pacientes/{pid}").text


def test_busca_paciente(cliente):
    cliente.post("/pacientes", data={"nome": "Joana Exemplo Teste"})
    r = cliente.get("/pacientes/busca", params={"q": "joana"})
    assert "Joana Exemplo Teste" in r.text


def test_catalogo_tem_estruturas(cliente):
    cat = cliente.get("/api/catalogo").json()
    lev = next(m for m in cat if m["principio_ativo"] == "Levetiracetam")
    assert lev["lme"] is True
    assert lev["apresentacoes"][0]["posologias"]
