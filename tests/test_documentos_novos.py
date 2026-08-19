"""Encaminhamento, atestado e relatório genérico — só dados fictícios."""
import io
import json

import pikepdf
import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import _qtds_meses, app


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "teste.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "SAIDA_DIR", tmp_path / "documentos")
    db.iniciar_banco()
    return TestClient(app)


def _novo_paciente(cliente, nome):
    r = cliente.post("/pacientes", data={"nome": nome}, follow_redirects=False)
    return r.headers["location"].rsplit("/", 1)[-1]


def test_encaminhamento_uma_pagina_por_especialidade(cliente):
    pid = _novo_paciente(cliente, "Rita Exemplo Encaminhada")
    r = cliente.post(f"/pacientes/{pid}/encaminhamento", data={
        "destino": "SECRETARIA MUNICIPAL DE SAÚDE",
        "esp": ["Fonoaudiologia", "Terapia Ocupacional"],
        "esp_outra": "Endocrinologia",
        "motivo": "Reabilitação após AVC isquêmico.",
        "cid10": "i63.9", "com_data": "com",
    }, follow_redirects=False)
    assert r.status_code == 303
    r = cliente.get(r.headers["location"])
    assert r.content[:5] == b"%PDF-"
    with pikepdf.open(io.BytesIO(r.content)) as pdf:
        assert len(pdf.pages) == 3            # 1 folha por especialidade


def test_encaminhamento_carta_sem_especialidade(cliente):
    """Cartinha de volta à origem (UPA/UBS): sem especialidade, só destinatário."""
    pid = _novo_paciente(cliente, "Ugo Exemplo Cartinha")
    r = cliente.post(f"/pacientes/{pid}/encaminhamento", data={
        "destino": "outro", "destino_outro": "UPA Central — equipe de origem",
        "titulo": "RESPOSTA — CONTRARREFERÊNCIA",
        "motivo": "Paciente avaliado nesta data; sem indicação cirúrgica no momento.",
        "com_data": "com",
    }, follow_redirects=False)
    assert r.status_code == 303
    r = cliente.get(r.headers["location"])
    assert r.content[:5] == b"%PDF-"
    with pikepdf.open(io.BytesIO(r.content)) as pdf:
        assert len(pdf.pages) == 1


def test_encaminhamento_sem_destino_nem_especialidade_nao_gera(cliente):
    pid = _novo_paciente(cliente, "Zoe Exemplo Vazia")
    r = cliente.post(f"/pacientes/{pid}/encaminhamento", data={
        "destino": "", "motivo": "x", "com_data": "com"}, follow_redirects=False)
    assert r.headers["location"].endswith("/encaminhamento")   # volta ao form


def test_encaminhamento_texto_longo_pagina_sem_sobrepor(cliente):
    pid = _novo_paciente(cliente, "Vera Exemplo Longa")
    motivo = "\n\n".join(f"Tópico {i}: " + "história clínica extensa do caso. " * 10
                         for i in range(25))
    r = cliente.post(f"/pacientes/{pid}/encaminhamento", data={
        "destino": "", "esp": ["Neurocirurgia"], "motivo": motivo,
        "cid10": "G40.1", "com_data": "com",
    }, follow_redirects=False)
    r = cliente.get(r.headers["location"])
    with pikepdf.open(io.BytesIO(r.content)) as pdf:
        assert len(pdf.pages) >= 2                # texto longo pagina


def test_relatorio_texto_longo_pagina(cliente):
    pid = _novo_paciente(cliente, "Walter Exemplo Extenso")
    texto = "\n".join("Evolução clínica detalhada do período. " * 8
                      for _ in range(60))
    r = cliente.post(f"/pacientes/{pid}/relatorio", data={
        "titulo": "RELATÓRIO MÉDICO", "texto": texto, "com_data": "com",
    }, follow_redirects=False)
    r = cliente.get(r.headers["location"])
    with pikepdf.open(io.BytesIO(r.content)) as pdf:
        assert len(pdf.pages) >= 2


def test_encaminhamento_regenera_apos_limpeza(cliente):
    pid = _novo_paciente(cliente, "Rui Exemplo Regenera")
    r = cliente.post(f"/pacientes/{pid}/encaminhamento", data={
        "destino": "", "esp": ["Psicologia"], "motivo": "Apoio psicológico.",
        "com_data": "sem",
    }, follow_redirects=False)
    url_pdf = r.headers["location"]
    cliente.get(url_pdf)
    for pdf in (config.SAIDA_DIR / f"paciente_{pid}").glob("*encaminhamento*.pdf"):
        pdf.unlink()                          # sistema leve: PDF antigo apagado
    r = cliente.get(url_pdf)
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"


def test_atestado_com_cid_autorizado(cliente):
    pid = _novo_paciente(cliente, "Beto Exemplo Atestado")
    r = cliente.post(f"/pacientes/{pid}/atestado", data={
        "titulo": "ATESTADO MÉDICO",
        "texto": "Atesto, para os devidos fins, que o(a) paciente Beto Exemplo "
                 "Atestado necessita de afastamento por 3 dia(s).",
        "incluir_cid": "sim", "cid10": "g40.1", "com_data": "com",
    }, follow_redirects=False)
    assert r.status_code == 303
    r = cliente.get(r.headers["location"])
    assert r.content[:5] == b"%PDF-"
    docs = cliente.get(f"/pacientes/{pid}").text
    assert "atestado" in docs


def test_atestado_sem_cid_quando_nao_autorizado(cliente):
    pid = _novo_paciente(cliente, "Bia Exemplo Sigilo")
    cliente.post(f"/pacientes/{pid}/atestado", data={
        "titulo": "DECLARAÇÃO", "texto": "Compareceu à consulta nesta data.",
        "cid10": "G40.1", "com_data": "sem",   # sem incluir_cid: CID não entra
    }, follow_redirects=False)
    con = db.conectar()
    try:
        doc = con.execute("SELECT conteudo_json FROM documentos WHERE tipo = "
                          "'atestado' ORDER BY id DESC").fetchone()
    finally:
        con.close()
    assert json.loads(doc["conteudo_json"])["cid10"] == ""


def test_relatorio_generico(cliente):
    pid = _novo_paciente(cliente, "Caio Exemplo Orientado")
    r = cliente.post(f"/pacientes/{pid}/relatorio", data={
        "titulo": "relatório de orientações — medicações em uso",
        "texto": "Medicações em uso:\n- Levetiracetam 500mg: 1 cp de 12/12h.",
        "com_data": "com",
    }, follow_redirects=False)
    assert r.status_code == 303
    r = cliente.get(r.headers["location"])
    assert r.content[:5] == b"%PDF-"


def test_form_relatorio_puxa_meds_da_ultima_receita(cliente):
    pid = _novo_paciente(cliente, "Davi Exemplo Meds")
    itens = [{"medicamento": "Donepezila 10mg - comprimido",
              "quantidade": "30 comprimidos", "posologia": "Tomar 1 à noite"}]
    cliente.post(f"/pacientes/{pid}/receita", data={
        "tipo": "controle_especial", "com_data": "sem", "acao": "salvar",
        "itens_json": json.dumps(itens)})
    r = cliente.get(f"/pacientes/{pid}/relatorio")
    assert "Donepezila 10mg" in r.text


def test_receita_uso_continuo_no_pdf(cliente):
    pid = _novo_paciente(cliente, "Elsa Exemplo Continua")
    itens = [{"medicamento": "Sertralina 50mg - comprimido",
              "quantidade": "30 comprimidos", "posologia": "Tomar 1 pela manhã"}]
    r = cliente.post(f"/pacientes/{pid}/receita", data={
        "tipo": "controle_especial", "uso_continuo": "sim", "com_data": "sem",
        "itens_json": json.dumps(itens)}, follow_redirects=False)
    r = cliente.get(r.headers["location"])
    assert r.content[:5] == b"%PDF-"
    con = db.conectar()
    try:
        doc = con.execute("SELECT conteudo_json FROM documentos WHERE tipo LIKE "
                          "'receita%' ORDER BY id DESC").fetchone()
    finally:
        con.close()
    assert json.loads(doc["conteudo_json"])["uso_continuo"] is True


def test_receita_longa_divide_em_folhas_completas(tmp_path, monkeypatch):
    """Muitos medicamentos/posologias longas não podem invadir a assinatura:
    a receita divide em folhas, cada uma com assinatura e bloco da farmácia."""
    from app.services.receita_pdf import ItemReceita, Receita, gerar_receita_pdf
    itens = [ItemReceita(f"Medicamento Exemplo {i} 500mg - comprimido",
                         "30 comprimidos",
                         "Tomar 1 comprimido pela manhã durante 7 dias;\n"
                         "Após, tomar 1 comprimido de 12 em 12 horas;\n"
                         "Após, tomar 2 comprimidos de 12 em 12 horas.")
             for i in range(6)]
    destino = tmp_path / "receita_longa.pdf"
    gerar_receita_pdf(Receita(paciente="Maria Exemplo da Silva", itens=itens,
                              vias=2, data="19/08/2026"), destino)
    with pikepdf.open(destino) as pdf:
        paginas = len(pdf.pages)
    assert paginas >= 4 and paginas % 2 == 0     # >1 folha por via, 2 vias iguais


def test_qtds_meses_titulacao():
    assert _qtds_meses("30") == ["30"]
    assert _qtds_meses("30 60 60") == ["30", "60", "60"]
    assert _qtds_meses("30;60,90/120") == ["30", "60", "90", "120"]
    assert _qtds_meses("") == [""]
    assert _qtds_meses(None) == [""]
