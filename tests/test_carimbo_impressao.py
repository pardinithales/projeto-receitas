"""Testes de carimbo (senha, janela 24h, PDF) e fila de impressão — dados fictícios."""
import json

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app
from app.services import imprimir


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "teste.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "documentos")
    monkeypatch.setattr(config, "CARIMBO_SENHA", "carimbo")
    monkeypatch.setattr(config, "CARIMBO_SENHA_MESTRA", "37900000000")
    db.iniciar_banco()
    return TestClient(app)


def _receita(cliente, pid, **extra):
    dados = {"tipo": "controle_especial", "via_administracao": "USO ORAL",
             "com_data": "sem", "acao": "gerar",
             "itens_json": json.dumps([{"medicamento": "Topiramato 50mg - comprimido",
                                        "quantidade": "60 comprimidos",
                                        "posologia": "Tomar 1 comprimido de 12/12h"}])}
    dados.update(extra)
    return cliente.post(f"/pacientes/{pid}/receita", data=dados,
                        follow_redirects=False)


def _pid(cliente, nome):
    r = cliente.post("/pacientes", data={"nome": nome}, follow_redirects=False)
    return r.headers["location"].rsplit("/", 1)[-1]


def test_carimbo_senha_errada_bloqueia(cliente):
    pid = _pid(cliente, "Teste Senha Errada")
    r = _receita(cliente, pid, carimbo="sim", senha_carimbo="errada")
    assert r.status_code == 403
    con = db.conectar()
    n = con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0]
    con.close()
    assert n == 0     # nada foi gerado


def test_carimbo_senha_certa_e_janela_24h(cliente):
    pid = _pid(cliente, "Teste Senha Certa")
    r = _receita(cliente, pid, carimbo="sim", senha_carimbo="carimbo")
    assert r.status_code == 303
    # segunda emissão SEM senha dentro da janela de 24h passa
    r2 = _receita(cliente, pid, carimbo="sim", senha_carimbo="")
    assert r2.status_code == 303
    con = db.conectar()
    payloads = [json.loads(d["conteudo_json"]) for d in
                con.execute("SELECT conteudo_json FROM documentos")]
    con.close()
    assert all(p["carimbo"] is True for p in payloads)


def test_carimbo_senha_mestra(cliente):
    pid = _pid(cliente, "Teste Senha Mestra")
    r = _receita(cliente, pid, carimbo="sim", senha_carimbo="37900000000")
    assert r.status_code == 303


def test_fila_impressao_retomada(cliente, monkeypatch, tmp_path):
    """Simula papel acabando no 2º documento e retomada depois."""
    chamadas = []

    def imprime_falhando_no_segundo(caminho, impressora):
        chamadas.append(caminho)
        if len(chamadas) == 2:
            return False, "tempo esgotado — impressora sem papel ou offline?"
        return True, "ok"

    monkeypatch.setattr(imprimir, "imprimir_pdf", imprime_falhando_no_segundo)
    pid = _pid(cliente, "Teste Impressao")
    docs = []
    for _ in range(3):
        r = _receita(cliente, pid)
        docs.append(int(r.headers["location"].split("/")[2]))

    con = db.conectar()
    for d in docs:
        caminho = con.execute("SELECT caminho_pdf FROM documentos WHERE id = ?",
                              (d,)).fetchone()["caminho_pdf"]
        imprimir.enfileirar(con, caminho, f"doc {d}", d)
    con.commit()
    con.close()

    resultado = imprimir.processar_fila()
    assert resultado["impressos"] == 1 and resultado["erro"]   # parou no 2º

    monkeypatch.setattr(imprimir, "imprimir_pdf", lambda c, i: (True, "ok"))
    resultado = imprimir.processar_fila()                       # retomada
    assert resultado["impressos"] == 2 and resultado["erro"] is None

    con = db.conectar()
    status = [r["status"] for r in con.execute("SELECT status FROM impressao_fila")]
    con.close()
    assert status.count("ok") == 3
