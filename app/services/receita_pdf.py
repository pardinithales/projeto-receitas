"""Geração do PDF de receita (controle especial e comum) fiel ao modelo do consultório."""
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

from app import config

LARGURA, ALTURA = A4
MARGEM_ESQ = 25 * mm
MARGEM_DIR = 20 * mm
LARGURA_UTIL = LARGURA - MARGEM_ESQ - MARGEM_DIR


@dataclass
class ItemReceita:
    medicamento: str          # "Levetiracetam 250mg - comprimido"
    quantidade: str           # "60 comprimidos" | "USO CONTÍNUO"
    posologia: str            # "Tomar 1 comprimido de 12 em 12 horas"


@dataclass
class Receita:
    paciente: str
    itens: list[ItemReceita] = field(default_factory=list)
    tipo: str = "controle_especial"   # controle_especial | comum
    via_administracao: str = "USO ORAL"
    data: str = ""                    # "18/08/2026" (vazio = sai sem campo de data)
    vias: int = 1                     # nº de folhas (SEM data: controladas = 2/mês)
    carimbo: bool = False             # aplica carimbo digital sobre a linha de assinatura


def _texto_quebrado(canvas: Canvas, texto: str, x: float, y: float, largura: float,
                    fonte: str = "Helvetica", tamanho: float = 11,
                    entrelinha: float = 4.5 * mm) -> float:
    # quebras de linha digitadas pelo usuário são respeitadas (titulação etc.)
    for paragrafo in texto.split("\n"):
        for linha in simpleSplit(paragrafo, fonte, tamanho, largura) or [""]:
            canvas.setFont(fonte, tamanho)
            canvas.drawString(x, y, linha)
            y -= entrelinha
    return y


def _cabecalho(c: Canvas, titulo: str, controle_especial: bool) -> float:
    if config.PAPEL_TIMBRADO.exists():
        c.drawImage(str(config.PAPEL_TIMBRADO), 0, 0, width=LARGURA, height=ALTURA,
                    preserveAspectRatio=False, mask=None)
    y = ALTURA - 45 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(LARGURA / 2, y, titulo)
    y -= 9 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGEM_ESQ, y, "IDENTIFICAÇÃO DO EMITENTE")
    if controle_especial:
        c.setFont("Helvetica", 9)
        c.drawRightString(LARGURA - MARGEM_DIR, y, "1ª VIA FARMÁCIA")
    y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGEM_ESQ, y, f"Dr. {config.MEDICO_NOME}")
    if controle_especial:
        c.setFont("Helvetica", 9)
        c.drawRightString(LARGURA - MARGEM_DIR, y, "2ª VIA PACIENTE")
    y -= 5.5 * mm
    c.setFont("Helvetica", 10)
    identificacao = config.MEDICO_CRM
    if config.MEDICO_RQE:
        identificacao += f" | RQE {config.MEDICO_RQE}"
    c.drawString(MARGEM_ESQ, y, identificacao)
    return y - 10 * mm


def _linha_medicamento(c: Canvas, item: ItemReceita, y: float) -> float:
    fonte, tam = "Helvetica-Bold", 11
    med = item.medicamento
    qtd = item.quantidade
    larg_qtd = c.stringWidth(qtd, fonte, tam)
    larg_med = c.stringWidth(med + " ", fonte, tam)
    c.setFont(fonte, tam)
    c.drawString(MARGEM_ESQ, y, med)
    x_ini = MARGEM_ESQ + larg_med
    x_fim = LARGURA - MARGEM_DIR - larg_qtd - 2 * mm
    if x_fim > x_ini:
        n = int((x_fim - x_ini) / c.stringWidth("_", fonte, tam))
        c.drawString(x_ini, y, "_" * max(n, 3))
    c.drawRightString(LARGURA - MARGEM_DIR, y, qtd)
    y -= 5.5 * mm
    y = _texto_quebrado(c, item.posologia, MARGEM_ESQ + 8 * mm, y,
                        LARGURA_UTIL - 8 * mm, "Helvetica", 11)
    return y - 3 * mm


def _bloco_comprador_fornecedor(c: Canvas, y_base: float) -> None:
    y = y_base
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGEM_ESQ, y, "IDENTIFICAÇÃO DO COMPRADOR")
    c.drawString(LARGURA / 2 + 10 * mm, y, "IDENTIFICAÇÃO DO FORNECEDOR")
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for rotulo in ("Nome: ______________________________________",
                   "Ident.: ____________ Órg. Emissor: __________",
                   "Endereço: __________________________________",
                   "Cidade: _________________________ UF: _____",
                   "Telefone: __________________________________"):
        c.drawString(MARGEM_ESQ, y, rotulo)
        y -= 5.5 * mm
    x2 = LARGURA / 2 + 10 * mm
    y2 = y_base - 17 * mm
    c.drawString(x2, y2, "_____________________________")
    c.drawString(x2, y2 - 4.5 * mm, "ASSINATURA DO FARMACÊUTICO")
    c.drawString(x2, y2 - 11 * mm, "______/______/______  DATA")


def desenhar_carimbo(c: Canvas, x_centro: float, y_linha: float) -> None:
    """Carimbo digital centrado sobre a linha de assinatura (fundo transparente,
    então pode ser grande como um carimbo real)."""
    if not config.CARIMBO_PATH.exists():
        return
    larg = 44 * mm
    alt = larg * 184 / 271          # proporção da imagem do carimbo
    c.drawImage(str(config.CARIMBO_PATH), x_centro - larg / 2, y_linha - 4 * mm,
                width=larg, height=alt, mask="auto")


def _assinatura(c: Canvas, y: float, data: str, carimbo: bool = False) -> None:
    c.setFont("Helvetica", 10)
    if data:
        c.drawString(MARGEM_ESQ, y + 8 * mm, f"{config.CIDADE_PADRAO}, {data}")
    # sem data: não imprime nada — receita sai limpa, sem campo de data
    x_centro = LARGURA * 0.62
    if carimbo:
        desenhar_carimbo(c, x_centro, y)
    c.setFont("Helvetica", 10)
    c.drawCentredString(x_centro, y, "________________________________________")
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x_centro, y - 5 * mm, f"Dr. {config.MEDICO_NOME}")
    c.setFont("Helvetica", 10)
    c.drawCentredString(x_centro, y - 10 * mm, "Médico Neurologista")
    c.drawCentredString(x_centro, y - 15 * mm, f"{config.MEDICO_CRM} | RQE {config.MEDICO_RQE}")


def gerar_receita_pdf(receita: Receita, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(destino), pagesize=A4)
    controle = receita.tipo == "controle_especial"
    titulo = "RECEITUÁRIO CONTROLE ESPECIAL" if controle else "RECEITUÁRIO MÉDICO"
    # nº de folhas vem calculado do guia (controlada = 2 por mês, mesmo COM data)
    n_vias = max(1, receita.vias)

    for _ in range(n_vias):
        y = _cabecalho(c, titulo, controle)
        c.setFont("Helvetica", 11)
        c.drawString(MARGEM_ESQ, y, f"Paciente: {receita.paciente}")
        y -= 9 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGEM_ESQ, y, receita.via_administracao)
        y -= 8 * mm

        for item in receita.itens:
            y = _linha_medicamento(c, item, y)

        y_comprador = 95 * mm
        _assinatura(c, y_comprador + 25 * mm, receita.data, receita.carimbo)
        if controle:
            _bloco_comprador_fornecedor(c, y_comprador - 10 * mm)
        c.showPage()

    c.save()
    return destino
