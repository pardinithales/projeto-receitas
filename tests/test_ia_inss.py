"""Testes do fluxo INSS e utilidades de IA — a API OpenAI é sempre mockada."""
import json

import pdfplumber
import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app
from app.services import ia


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "teste.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "documentos")
    db.iniciar_banco()
    return TestClient(app)


def test_limpar_texto_remove_travessoes():
    assert ia.limpar_texto("dor lombar — crônica") == "dor lombar, crônica"
    assert ia.limpar_texto("dose 30–60 mg") == "dose 30-60 mg"


def test_criterios_por_cid_cobrem_principais():
    for cid in ("G40", "G70", "G35", "G61", "G30", "R52", "G20"):
        assert cid in ia.CRITERIOS_POR_CID


def test_fluxo_inss_com_ia_mockada(cliente, monkeypatch):
    monkeypatch.setattr(ia, "gerar_relatorio_inss", lambda *a, **k: {
        "texto": "Paciente com epilepsia focal estrutural em seguimento. "
                 "Mantém crises semanais apesar de tratamento otimizado.",
        "cids": [{"codigo": "G40.1", "descricao": "Epilepsia focal sintomática"}]})
    r = cliente.post("/pacientes", data={"nome": "Caso Exemplo Inss"},
                     follow_redirects=False)
    pid = r.headers["location"].rsplit("/", 1)[-1]

    r = cliente.post(f"/pacientes/{pid}/inss",
                     data={"dados": "evolucoes coladas aqui", "modo": "padrao"})
    assert r.status_code == 200
    assert "Mantém crises semanais" in r.text          # tela de revisão
    assert "G40.1" in r.text

    r = cliente.post(f"/pacientes/{pid}/inss/pdf", data={
        "dados": "evolucoes", "texto": "Texto final revisado pelo médico.",
        "cids_json": json.dumps(["G40.1 - Epilepsia focal sintomática"]),
    }, follow_redirects=False)
    pdf = cliente.get(r.headers["location"])
    assert pdf.content[:5] == b"%PDF-"

    con = db.conectar()
    doc = con.execute("SELECT * FROM documentos WHERE tipo = 'relatorio_inss'").fetchone()
    con.close()
    with pdfplumber.open(doc["caminho_pdf"]) as p:
        texto = p.pages[0].extract_text()
    assert "RELATÓRIO PARA FINS PREVIDENCIÁRIOS" in texto
    assert "Página 1 de 1" in texto
    assert "CID-10: G40.1" in texto


def test_inss_erro_de_api_preserva_dados(cliente, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("timeout simulado")
    monkeypatch.setattr(ia, "gerar_relatorio_inss", explode)
    r = cliente.post("/pacientes", data={"nome": "Caso Erro Api"},
                     follow_redirects=False)
    pid = r.headers["location"].rsplit("/", 1)[-1]
    r = cliente.post(f"/pacientes/{pid}/inss",
                     data={"dados": "TEXTO_COLADO_IMPORTANTE", "modo": "padrao"})
    assert r.status_code == 502
    assert "TEXTO_COLADO_IMPORTANTE" in r.text     # nada se perde


def test_relatorio_previdenciario_multipagina(tmp_path):
    from app.services.documentos_pdf import (RelatorioPrevidenciario,
                                             gerar_relatorio_previdenciario_pdf)
    rel = RelatorioPrevidenciario(
        paciente="Multi Pagina Exemplo",
        texto="Linha de conteúdo clínico repetida para forçar quebra. " * 200,
        cids=["G35 - Esclerose múltipla"], data="18/08/2026")
    pdf = gerar_relatorio_previdenciario_pdf(rel, tmp_path / "prev.pdf")
    with pdfplumber.open(pdf) as p:
        assert len(p.pages) >= 2
        for i, pg in enumerate(p.pages, start=1):
            t = pg.extract_text()
            assert "Multi Pagina Exemplo" in t          # identificação em toda página
            assert f"Página {i} de {len(p.pages)}" in t  # paginação
