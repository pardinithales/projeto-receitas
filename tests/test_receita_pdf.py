"""Testes da geração de receita em PDF — somente dados fictícios."""
from pathlib import Path

import pdfplumber
import pytest

from app.services.receita_pdf import ItemReceita, Receita, gerar_receita_pdf


@pytest.fixture
def receita_exemplo() -> Receita:
    return Receita(
        paciente="Maria Exemplo da Silva",
        itens=[
            ItemReceita("Levetiracetam 250mg - comprimido", "120 comprimidos",
                        "Tomar 2 comprimidos de 12 em 12 horas"),
            ItemReceita("Clobazam 10mg - comprimido", "30 comprimidos",
                        "Tomar 1 comprimido à noite"),
            ItemReceita("Levodopa + Benserazida 100/25mg BD", "USO CONTÍNUO",
                        "Tomar 1 + ½ (um e meio) às 07:00; 1 comprimido às 13:00 "
                        "(2 horas após almoçar); 1 comprimido às 17:00"),
        ],
        data="18/08/2026",
    )


def _texto_pdf(caminho: Path) -> str:
    with pdfplumber.open(caminho) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_controle_especial_estrutura(tmp_path: Path, receita_exemplo: Receita):
    pdf = gerar_receita_pdf(receita_exemplo, tmp_path / "r.pdf")
    texto = _texto_pdf(pdf)
    assert "RECEITUÁRIO CONTROLE ESPECIAL" in texto
    assert "1ª VIA FARMÁCIA" in texto
    assert "2ª VIA PACIENTE" in texto
    assert "IDENTIFICAÇÃO DO COMPRADOR" in texto
    assert "IDENTIFICAÇÃO DO FORNECEDOR" in texto
    assert "ASSINATURA DO FARMACÊUTICO" in texto


def test_conteudo_da_receita(tmp_path: Path, receita_exemplo: Receita):
    pdf = gerar_receita_pdf(receita_exemplo, tmp_path / "r.pdf")
    texto = _texto_pdf(pdf)
    assert "Maria Exemplo da Silva" in texto
    assert "USO ORAL" in texto
    for item in receita_exemplo.itens:
        assert item.medicamento in texto
        assert item.quantidade in texto
        # posologia pode quebrar de linha: conferir por fragmento inicial
        assert item.posologia[:25] in texto.replace("\n", " ")


def test_assinatura_e_data(tmp_path: Path, receita_exemplo: Receita):
    pdf = gerar_receita_pdf(receita_exemplo, tmp_path / "r.pdf")
    texto = _texto_pdf(pdf)
    assert "Médico Neurologista" in texto
    assert "18/08/2026" in texto


def test_sem_data_nao_imprime_campo_de_data(tmp_path: Path, receita_exemplo: Receita):
    receita_exemplo.data = ""
    pdf = gerar_receita_pdf(receita_exemplo, tmp_path / "r.pdf")
    texto = _texto_pdf(pdf)
    assert "Data: ___" not in texto
    assert "18/08/2026" not in texto


def test_receita_comum_sem_blocos_de_controlada(tmp_path: Path):
    receita = Receita(
        paciente="João Exemplo de Souza",
        itens=[ItemReceita("Propranolol 40mg - comprimido", "60 comprimidos",
                           "Tomar 1 comprimido de 12 em 12 horas")],
        tipo="comum",
    )
    pdf = gerar_receita_pdf(receita, tmp_path / "r.pdf")
    texto = _texto_pdf(pdf)
    assert "RECEITUÁRIO MÉDICO" in texto
    assert "RECEITUÁRIO CONTROLE ESPECIAL" not in texto
    assert "IDENTIFICAÇÃO DO COMPRADOR" not in texto


def test_uso_endovenoso(tmp_path: Path):
    receita = Receita(
        paciente="Ana Exemplo Pereira",
        itens=[ItemReceita("Imunoglobulina Humana Frasco 5 gramas", "28 frascos no total",
                           "Dias 1, 2 e 3: 6 frascos/dia; dias 4 e 5: 5 frascos/dia.")],
        via_administracao="USO ENDOVENOSO, EM BOMBA DE INFUSÃO CONTÍNUA (BIC)",
    )
    pdf = gerar_receita_pdf(receita, tmp_path / "r.pdf")
    texto = _texto_pdf(pdf)
    assert "USO ENDOVENOSO" in texto
