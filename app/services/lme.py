"""Preenchimento do LME oficial (PDF AcroForm) via pikepdf.

Mapa de campos e estados dos radios: docs/lme-campos.md.
Estados decifrados por posição geométrica dos widgets + exemplar real:
  Tratamentos prévios?: /0 = SIM, /1 = NÃO
  Incapaz?:             /0 = NÃO, /1 = SIM
  dados complementares (preenchido por): /0 paciente /1 mãe /2 responsável /3 médico /4 outro
  Radio Button1 (raça/cor): /0 Branca /1 Amarela /2 Preta /3 Indígena /4 Parda
  Documentos: /CPF ou /CNS
"""
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf

from app import config

TEMPLATE_LME = config.TEMPLATES_DIR / "lme" / "lme_oficial.pdf"

# Campos de quantidade (mês 1..6) por índice de medicamento (0..5)
CAMPOS_QTD = [
    ["Text6", "Text7", "Text8", "Text6a", "Text7a", "Text8a"],
    ["Text10", "Text11", "Text12", "Text10a", "Text11a", "Text12a"],
    ["Text14", "Text15", "Text16", "Text14a", "Text15a", "Text16a"],
    ["Text18", "Text19", "Text20", "Text6b", "Text7b", "Text8b"],
    ["Text22", "Text23", "Text24", "Text10b", "Text11b", "Text12b"],
    ["Text22a", "Text23a", "Text24a", "Text14b", "Text15b", "Text16b"],
]

RACA_COR = {"branca": "/0", "amarela": "/1", "preta": "/2", "indígena": "/3",
            "indigena": "/3", "parda": "/4"}


@dataclass
class MedicamentoLME:
    descricao: str            # "Levetiracetam 750mg - comprimido"
    qtd_meses: list[str] = field(default_factory=list)   # 6 valores (repete o último se faltar)


@dataclass
class DadosLME:
    paciente: str
    nome_mae: str = ""
    peso_kg: str = ""
    altura_cm: str = ""
    medicamentos: list[MedicamentoLME] = field(default_factory=list)
    cid10: str = ""
    diagnostico: str = ""
    anamnese: str = ""
    tratamentos_previos: str = ""      # vazio = radio NÃO
    incapaz: bool = False
    nome_responsavel: str = ""
    raca_cor: str = ""
    telefone: str = ""
    documento_tipo: str = ""           # "CPF" | "CNS"
    documento_numero: str = ""
    email: str = ""
    data: str = ""                     # dd/mm/aaaa
    carimbo: bool = False              # carimbo digital nos 2 campos de assinatura


def _set_radio(pdf: pikepdf.Pdf, nome: str, estado: str) -> None:
    for f in pdf.Root.AcroForm.Fields:
        if str(f.get("/T", "")) == nome:
            f.V = pikepdf.Name(estado)
            for kid in f.get("/Kids", []):
                ap = kid.get("/AP")
                estados = set()
                if ap is not None and ap.get("/N") is not None:
                    estados = {str(s) for s in ap.get("/N").keys()}
                kid.AS = pikepdf.Name(estado if estado in estados else "/Off")
            return


def _set_texto(campos: dict, nome: str, valor: str) -> None:
    if not valor:
        return
    f = campos.get(nome)
    if f is not None:
        f.V = pikepdf.String(str(valor))
        if "/AP" in f:
            del f["/AP"]      # força o leitor a redesenhar com o novo valor


def _normalizar(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _melhor_opcao_oficial(descricao: str, opcoes: list[str]) -> str | None:
    """Casa 'Levetiracetam 750mg - comprimido' com a opção oficial do dropdown CEAF."""
    import re
    desc = _normalizar(descricao)
    principio = desc.split()[0]
    doses = set(re.findall(r"[\d,.]+", desc))
    melhores = []
    for op in opcoes:
        op_n = _normalizar(op)
        if principio not in op_n:
            continue
        doses_op = set(re.findall(r"[\d,.]+", op_n))
        melhores.append((len(doses & doses_op), op))
    if not melhores:
        return None
    return max(melhores, key=lambda x: x[0])[1]


def preencher_lme(dados: DadosLME, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    pdf = pikepdf.open(TEMPLATE_LME)
    pdf.Root.AcroForm.NeedAppearances = True

    campos: dict = {}
    for page in pdf.pages:
        for annot in page.get("/Annots", []):
            t = annot.get("/T")
            if t is not None:
                campos[str(t)] = annot

    _set_texto(campos, "CNES", config.LME_CNES)
    _set_texto(campos, "Nome do estabelecimento de saúde", config.LME_ESTABELECIMENTO)
    _set_texto(campos, "Nome do paciente", dados.paciente)
    _set_texto(campos, "Nome da mãe do paciente", dados.nome_mae)
    _set_texto(campos, "Peso", dados.peso_kg)
    _set_texto(campos, "Altura", dados.altura_cm)
    _set_texto(campos, "CID", dados.cid10)
    _set_texto(campos, "Diagnóstico", dados.diagnostico)
    _set_texto(campos, "Anamnese", dados.anamnese)
    _set_texto(campos, "tratamentos prévios", dados.tratamentos_previos)
    _set_texto(campos, "Nome do Responsável", dados.nome_responsavel)
    _set_texto(campos, "Text46", config.MEDICO_NOME)
    _set_texto(campos, "TextCNS", config.MEDICO_CNS)
    _set_texto(campos, "Today", dados.data)
    _set_texto(campos, "Telefone I", dados.telefone)
    _set_texto(campos, "email", dados.email)
    _set_texto(campos, "Nome do preencher", config.MEDICO_NOME)

    # linha 1 tem campo de texto livre (med1); linhas 2-6 só têm o dropdown
    # oficial do CEAF (327 opções, não editável) — casar com a opção oficial.
    for i, med in enumerate(dados.medicamentos[:6]):
        if i == 0:
            _set_texto(campos, "med1", med.descricao)
        else:
            sel = campos.get(f"Selecao med {i + 1}")
            if sel is not None:
                opcoes = [str(o) for o in sel.get("/Opt", [])]
                oficial = _melhor_opcao_oficial(med.descricao, opcoes)
                _set_texto(campos, f"Selecao med {i + 1}", oficial or med.descricao)
        qtds = med.qtd_meses or [""]
        for m, campo in enumerate(CAMPOS_QTD[i]):
            valor = qtds[m] if m < len(qtds) else qtds[-1]
            _set_texto(campos, campo, valor)

    _set_radio(pdf, "Tratamentos prévios?", "/0" if dados.tratamentos_previos else "/1")
    _set_radio(pdf, "Incapaz?", "/1" if dados.incapaz else "/0")
    _set_radio(pdf, "dados complementares", "/3")   # preenchido pelo médico solicitante
    if dados.raca_cor.lower() in RACA_COR:
        _set_radio(pdf, "Radio Button1", RACA_COR[dados.raca_cor.lower()])
    if dados.documento_tipo in ("CPF", "CNS"):
        _set_radio(pdf, "Documentos", f"/{dados.documento_tipo}")
        _set_texto(campos, "Text25a", dados.documento_numero)

    # Widgets de tela (botões, dropdowns) não podem aparecer no PDF final:
    # escondemos todos e escrevemos os medicamentos como conteúdo da página.
    textos_overlay = _esconder_widgets_e_medir(pdf, dados)
    _aplicar_overlay(pdf, textos_overlay, com_carimbo=dados.carimbo)

    pdf.save(destino)
    return destino


# Nomes de widgets que são só de tela (nunca devem sair na impressão)
WIDGETS_DE_TELA = {"MENU", "Salvar como", "Busca CNES", "Hoje",
                   "Digitar manualmente", "Listar medicamentos", "Text2", "suporte"}

# Carimbo: campo 17 (assinatura do médico) e campo 23 (responsável preenchimento)
# (fundo transparente: pode ocupar o quadro como um carimbo real)
POSICOES_CARIMBO = [(420, 178), (420, 24)]      # canto inferior esquerdo
CARIMBO_LARGURA = 100                            # pontos (~35mm)


def _esconder_widgets_e_medir(pdf: pikepdf.Pdf, dados: DadosLME) -> list[tuple]:
    """Esconde botões/dropdowns (F=2) e devolve os textos de medicamento com a
    posição da linha correspondente para desenhar como conteúdo fixo."""
    textos: list[tuple] = []
    for page in pdf.pages:
        for annot in page.get("/Annots", []) or []:
            t = annot.get("/T")
            if t is None:
                continue
            nome = str(t)
            esconder = (nome in WIDGETS_DE_TELA or nome.startswith("Limpar")
                        or nome.startswith("PCDT") or nome.startswith("Selecao med"))
            if nome == "med1" or nome.startswith("Selecao med"):
                idx = 0 if nome == "med1" else int(nome.rsplit(" ", 1)[1]) - 1
                if idx < len(dados.medicamentos):
                    r = [float(x) for x in annot.get("/Rect")]
                    if nome == "med1" or idx > 0:   # linha 1 usa o rect do med1
                        textos.append((dados.medicamentos[idx].descricao,
                                       min(r[0], r[2]) + 3,
                                       min(r[1], r[3]) + 5))
                if nome == "med1":
                    esconder = True   # o texto sai como conteúdo da página
            if esconder:
                annot.F = 2          # hidden: não aparece na tela nem na impressão
    return textos


def _aplicar_overlay(pdf: pikepdf.Pdf, textos: list[tuple],
                     com_carimbo: bool) -> None:
    import io

    from reportlab.pdfgen.canvas import Canvas as RLCanvas

    if not textos and not (com_carimbo and config.CARIMBO_PATH.exists()):
        return
    buf = io.BytesIO()
    c = RLCanvas(buf, pagesize=(595.32, 841.92))
    c.setFont("Helvetica", 8)
    for texto, x, y in textos:
        c.drawString(x, y, texto[:80])
    if com_carimbo and config.CARIMBO_PATH.exists():
        alt = CARIMBO_LARGURA * 184 / 271
        for x, y in POSICOES_CARIMBO:
            c.drawImage(str(config.CARIMBO_PATH), x, y,
                        width=CARIMBO_LARGURA, height=alt, mask="auto")
    c.showPage()
    c.save()
    buf.seek(0)
    overlay = pikepdf.open(buf)
    pdf.pages[0].add_overlay(overlay.pages[0])
