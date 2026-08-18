"""Testes de LME, pedido de exames, múltiplas vias e anti-duplicata — dados fictícios."""
import json

import pdfplumber
import pikepdf
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


def _novo_paciente(cliente, nome="Maria Exemplo da Silva"):
    r = cliente.post("/pacientes", data={"nome": nome}, follow_redirects=False)
    return r.headers["location"].rsplit("/", 1)[-1]


def test_lme_valida_obrigatorios(cliente):
    pid = _novo_paciente(cliente)
    r = cliente.post(f"/pacientes/{pid}/lme", data={
        "meds_json": json.dumps([{"descricao": "Levetiracetam 750mg - comprimido",
                                  "qtd_mensal": "60"}]),
        "cid10": "G40.1", "diagnostico": "", "anamnese": "",
    })
    assert r.status_code == 422
    assert "Faltam campos obrigatórios" in r.text


def test_lme_gera_pdf_preenchido(cliente):
    pid = _novo_paciente(cliente)
    r = cliente.post(f"/pacientes/{pid}/lme", data={
        "nome_mae": "Joana Exemplo", "peso_kg": "70", "altura_cm": "165",
        "cns": "700000000000000", "raca_cor": "Parda",
        "meds_json": json.dumps([
            {"descricao": "Levetiracetam 750mg - comprimido", "qtd_mensal": "60"},
            {"descricao": "Clobazam 10mg - comprimido", "qtd_mensal": "30"}]),
        "cid10": "G40.1", "diagnostico": "Epilepsia focal",
        "anamnese": "Paciente fictícia para teste.", "com_data": "com",
    }, follow_redirects=False)
    assert r.status_code == 303
    pdf_resp = cliente.get(r.headers["location"])
    assert pdf_resp.content[:5] == b"%PDF-"

    con = db.conectar()
    caminho = con.execute("SELECT caminho_pdf FROM documentos WHERE tipo = 'lme'"
                          ).fetchone()["caminho_pdf"]
    con.close()
    pdf = pikepdf.open(caminho)
    valores = {}
    for page in pdf.pages:
        for a in page.get("/Annots", []):
            if a.get("/T") is not None and a.get("/V") is not None:
                valores[str(a.get("/T"))] = str(a.get("/V"))
    assert valores["Nome do paciente"] == "MARIA EXEMPLO DA SILVA"
    assert valores["med1"] == "Levetiracetam 750mg - comprimido"
    assert valores["Selecao med 2"] == "Clobazam 10 mg (comprimido)"
    assert valores["Text6"] == "60" and valores["Text8a"] == "60"
    assert valores["CID"] == "G40.1"


def test_lme_alzheimer_exige_meem_cdr_escolaridade(cliente):
    pid = _novo_paciente(cliente)
    r = cliente.post(f"/pacientes/{pid}/lme", data={
        "nome_mae": "Joana Exemplo", "peso_kg": "70", "altura_cm": "165",
        "meds_json": json.dumps([{"descricao": "Donepezila 10mg - comprimido",
                                  "qtd_mensal": "30"}]),
        "cid10": "G30.1", "diagnostico": "Doença de Alzheimer", "anamnese": "Teste.",
    })
    assert r.status_code == 422
    assert "MEEM" in r.text and "CDR" in r.text


def test_lme_com_relatorio_alto_custo(cliente):
    pid = _novo_paciente(cliente)
    cliente.post(f"/pacientes/{pid}/lme", data={
        "nome_mae": "Joana Exemplo", "peso_kg": "70", "altura_cm": "165",
        "meds_json": json.dumps([{"descricao": "Donepezila 10mg - comprimido",
                                  "qtd_mensal": "30"}]),
        "cid10": "G30.1", "diagnostico": "Doença de Alzheimer",
        "anamnese": "Teste.", "gerar_relatorio": "sim",
        "texto_relatorio": "Texto fictício do relatório para alto custo.",
        "meem": "14", "cdr": "2", "escolaridade_anos": "4",
    })
    con = db.conectar()
    tipos = [r["tipo"] for r in con.execute(
        "SELECT tipo FROM documentos WHERE paciente_id = ?", (pid,))]
    lme = con.execute("SELECT * FROM lme_dados WHERE paciente_id = ?", (pid,)).fetchone()
    escalas = [r["tipo"] for r in con.execute(
        "SELECT tipo FROM escalas WHERE paciente_id = ?", (pid,))]
    con.close()
    assert "lme" in tipos and "relatorio_alto_custo" in tipos
    assert "MEEM" in escalas and "CDR" in escalas   # escores salvos p/ renovação


def test_pedido_exames_multiplas_datas(cliente):
    pid = _novo_paciente(cliente)
    r = cliente.post(f"/pacientes/{pid}/exames", data={
        "exames_json": json.dumps([{"nome": "Hemograma completo", "material": "sangue"},
                                   {"nome": "TGO/TGP", "material": "sangue"}]),
        "meses_json": json.dumps([0, 3, 6]),
        "indicacao": "monitorização fictícia", "com_data": "com",
    }, follow_redirects=False)
    pdf_resp = cliente.get(r.headers["location"])
    con = db.conectar()
    caminho = con.execute("SELECT caminho_pdf FROM documentos WHERE tipo = 'pedido_exames'"
                          ).fetchone()["caminho_pdf"]
    con.close()
    with pdfplumber.open(caminho) as pdf:
        assert len(pdf.pages) == 3     # hoje, +3, +6
        texto = pdf.pages[0].extract_text()
        assert "Hemograma completo" in texto
        assert "Realizar a partir de" in texto


def test_receita_multiplas_vias_sem_data(cliente):
    pid = _novo_paciente(cliente)
    r = cliente.post(f"/pacientes/{pid}/receita", data={
        "tipo": "controle_especial", "via_administracao": "USO ORAL",
        "com_data": "sem", "vias": "5", "acao": "gerar",
        "itens_json": json.dumps([{"medicamento": "Topiramato 50mg - comprimido",
                                   "quantidade": "60 comprimidos",
                                   "posologia": "Tomar 1 comprimido de 12 em 12 horas"}]),
    }, follow_redirects=False)
    cliente.get(r.headers["location"])
    con = db.conectar()
    caminho = con.execute("SELECT caminho_pdf FROM documentos ORDER BY id DESC"
                          ).fetchone()["caminho_pdf"]
    con.close()
    with pdfplumber.open(caminho) as pdf:
        assert len(pdf.pages) == 5


def test_anti_duplicata_de_nomes(cliente):
    pid1 = _novo_paciente(cliente, "Jose da Silva Exemplo")
    pid2 = _novo_paciente(cliente, "  josé  DA  silva exemplo ")
    assert pid1 == pid2   # não cria duplicata por acento/caixa/espaços


def test_busca_por_tags(cliente):
    pid = _novo_paciente(cliente, "Paciente Com Tag")
    cliente.post(f"/pacientes/{pid}/editar", data={
        "nome": "Paciente Com Tag", "tags": "epilepsia focal, meningioma"})
    r = cliente.get("/pacientes/busca", params={"q": "meningioma"})
    assert "Paciente Com Tag" in r.text