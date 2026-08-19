"""Relatório médico (farmácia de alto custo) e solicitação de exames em PDF."""
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

from app import config
from app.services.receita_pdf import (LARGURA, ALTURA, MARGEM_ESQ, MARGEM_DIR,
                                      LARGURA_UTIL, desenhar_carimbo)


def _fundo_timbrado(c: Canvas) -> None:
    if config.PAPEL_TIMBRADO.exists():
        c.drawImage(str(config.PAPEL_TIMBRADO), 0, 0, width=LARGURA, height=ALTURA,
                    preserveAspectRatio=False)


def _paragrafo(c: Canvas, texto: str, x: float, y: float, largura: float,
               fonte: str = "Helvetica", tamanho: float = 11,
               entrelinha: float = 5.2 * mm) -> float:
    for bloco in texto.split("\n"):
        for linha in simpleSplit(bloco, fonte, tamanho, largura) or [""]:
            c.setFont(fonte, tamanho)
            c.drawString(x, y, linha)
            y -= entrelinha
    return y


def _assinatura_rodape(c: Canvas, y: float = 55 * mm, data: str = "",
                       carimbo: bool = False) -> None:
    c.setFont("Helvetica", 10)
    if data:
        c.drawString(MARGEM_ESQ, y + 10 * mm, f"{config.CIDADE_PADRAO}, {data}")
    x = LARGURA * 0.62
    if carimbo:
        desenhar_carimbo(c, x, y)
    c.setFont("Helvetica", 10)
    c.drawCentredString(x, y, "________________________________________")
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x, y - 5 * mm, f"Dr. {config.MEDICO_NOME}")
    c.setFont("Helvetica", 10)
    c.drawCentredString(x, y - 10 * mm, "Médico Neurologista")
    c.drawCentredString(x, y - 15 * mm, f"{config.MEDICO_CRM} | RQE {config.MEDICO_RQE}")


@dataclass
class RelatorioMedico:
    paciente: str
    texto: str
    cid10: str = ""
    titulo: str = "RELATÓRIO MÉDICO"
    data: str = ""
    carimbo: bool = False


def gerar_relatorio_pdf(rel: RelatorioMedico, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(destino), pagesize=A4)
    _fundo_timbrado(c)
    y = ALTURA - 45 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(LARGURA / 2, y, rel.titulo)
    y -= 12 * mm
    c.setFont("Helvetica", 11)
    c.drawString(MARGEM_ESQ, y, f"Paciente: {rel.paciente}")
    y -= 10 * mm
    y = _paragrafo(c, rel.texto, MARGEM_ESQ, y, LARGURA_UTIL)
    if rel.cid10:
        y -= 4 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGEM_ESQ, y, f"CID-10: {rel.cid10}")
    _assinatura_rodape(c, data=rel.data, carimbo=rel.carimbo)
    c.showPage()
    c.save()
    return destino


@dataclass
class RelatorioPrevidenciario:
    paciente: str
    texto: str
    cids: list[str] = field(default_factory=list)     # ["G40.1 - Epilepsia focal", ...]
    data: str = ""
    documento: str = ""                                # RG/CPF do paciente, se houver
    carimbo: bool = False


def gerar_relatorio_previdenciario_pdf(rel: RelatorioPrevidenciario,
                                       destino: Path) -> Path:
    """RELATÓRIO PARA FINS PREVIDENCIÁRIOS: letra menor, sem bloco de farmácia,
    paginação e identificação do paciente em TODAS as páginas."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    FONTE, TAM, ENTRE = "Helvetica", 10, 4.6 * mm
    Y_TOPO, Y_FUNDO = ALTURA - 52 * mm, 60 * mm

    # quebra parágrafos em linhas para paginar (2 passadas: contar, depois desenhar)
    linhas: list[str] = []
    for par in rel.texto.split("\n"):
        par = par.strip()
        if not par:
            linhas.append("")
            continue
        linhas.extend(simpleSplit(par, FONTE, TAM, LARGURA_UTIL))
        linhas.append("")
    if rel.cids:
        linhas.append("")
        for cid in rel.cids:
            linhas.append(f"CID-10: {cid}")

    por_pagina = int((Y_TOPO - Y_FUNDO) / ENTRE)
    paginas = [linhas[i:i + por_pagina] for i in range(0, len(linhas), por_pagina)] or [[]]
    total = len(paginas)

    c = Canvas(str(destino), pagesize=A4)
    for num, bloco in enumerate(paginas, start=1):
        _fundo_timbrado(c)
        y = ALTURA - 40 * mm
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(LARGURA / 2, y, "RELATÓRIO PARA FINS PREVIDENCIÁRIOS")
        y -= 7 * mm
        c.setFont("Helvetica", 9)
        ident = f"Paciente: {rel.paciente}"
        if rel.documento:
            ident += f"  |  Documento: {rel.documento}"
        c.drawString(MARGEM_ESQ, y, ident)
        c.drawRightString(LARGURA - MARGEM_DIR, y, f"Página {num} de {total}")
        y = Y_TOPO
        for linha in bloco:
            if linha:
                c.setFont(FONTE, TAM)
                c.drawString(MARGEM_ESQ, y, linha)
            y -= ENTRE
        if num == total:
            # 52mm: acima da barra rosa e do site do papel timbrado
            _assinatura_rodape(c, y=52 * mm, data=rel.data, carimbo=rel.carimbo)
        else:
            c.setFont("Helvetica-Oblique", 8)
            c.drawCentredString(LARGURA / 2, 30 * mm, "continua na próxima página")
        c.showPage()
    c.save()
    return destino


@dataclass
class Encaminhamento:
    paciente: str
    especialidades: list[str] = field(default_factory=list)   # 1 página por especialidade
    destino: str = ""             # ex.: "SECRETARIA MUNICIPAL DE SAÚDE" ou serviço/colega
    motivo: str = ""
    cid10: str = ""
    data: str = ""
    carimbo: bool = False


def gerar_encaminhamento_pdf(enc: Encaminhamento, destino_pdf: Path) -> Path:
    """Uma página por especialidade solicitada (cada serviço fica com a sua)."""
    destino_pdf.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(destino_pdf), pagesize=A4)
    for esp in (enc.especialidades or [""]):
        _fundo_timbrado(c)
        y = ALTURA - 45 * mm
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(LARGURA / 2, y, "ENCAMINHAMENTO MÉDICO")
        y -= 12 * mm
        y = _paragrafo(c, f"De: Neurologia — Dr. {config.MEDICO_NOME} "
                          f"({config.MEDICO_CRM} | RQE {config.MEDICO_RQE})",
                       MARGEM_ESQ, y, LARGURA_UTIL, tamanho=10)
        para = " — ".join(p for p in (enc.destino, esp) if p)
        y = _paragrafo(c, f"Para: {para}", MARGEM_ESQ, y, LARGURA_UTIL,
                       fonte="Helvetica-Bold", tamanho=11)
        y -= 2 * mm
        c.setFont("Helvetica", 11)
        c.drawString(MARGEM_ESQ, y, f"Paciente: {enc.paciente}")
        y -= 10 * mm
        texto = ("Encaminho o(a) paciente para avaliação e acompanhamento com "
                 f"{esp or 'a especialidade indicada'}.")
        if enc.motivo:
            texto += f"\n\nMotivo / resumo clínico: {enc.motivo}"
        y = _paragrafo(c, texto, MARGEM_ESQ, y, LARGURA_UTIL)
        if enc.cid10:
            y -= 2 * mm
            c.setFont("Helvetica-Bold", 11)
            c.drawString(MARGEM_ESQ, y, f"CID-10: {enc.cid10}")
            y -= 8 * mm
        y -= 2 * mm
        y = _paragrafo(c, "Agradeço a atenção e coloco-me à disposição para "
                          "esclarecimentos.", MARGEM_ESQ, y, LARGURA_UTIL)
        _assinatura_rodape(c, data=enc.data, carimbo=enc.carimbo)
        c.showPage()
    c.save()
    return destino_pdf


@dataclass
class Atestado:
    paciente: str
    texto: str                    # já vem completo (modelos montados na tela)
    titulo: str = "ATESTADO MÉDICO"
    cid10: str = ""               # só sai se o paciente autorizar
    data: str = ""
    carimbo: bool = False


def gerar_atestado_pdf(at: Atestado, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(destino), pagesize=A4)
    _fundo_timbrado(c)
    y = ALTURA - 55 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(LARGURA / 2, y, at.titulo)
    y -= 16 * mm
    y = _paragrafo(c, at.texto, MARGEM_ESQ, y, LARGURA_UTIL,
                   tamanho=12, entrelinha=7 * mm)
    if at.cid10:
        y -= 4 * mm
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGEM_ESQ, y, f"CID-10: {at.cid10}")
    _assinatura_rodape(c, data=at.data, carimbo=at.carimbo)
    c.showPage()
    c.save()
    return destino


@dataclass
class ExameSolicitado:
    nome: str
    material: str = ""            # "sangue", "urina", "imagem"...


@dataclass
class PedidoExames:
    paciente: str
    exames: list[ExameSolicitado] = field(default_factory=list)
    indicacao: str = ""           # justificativa clínica / CID
    datas: list[str] = field(default_factory=list)   # 1 página por data ("" = sem data)
    observacao: str = "Realizar preferencialmente no laboratório de sua cidade."
    carimbo: bool = False


def gerar_pedido_exames_pdf(pedido: PedidoExames, destino: Path) -> Path:
    """Uma página por data (ex.: pedidos para 3, 6, 9 e 12 meses)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(destino), pagesize=A4)
    for data in (pedido.datas or [""]):
        _fundo_timbrado(c)
        y = ALTURA - 45 * mm
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(LARGURA / 2, y, "SOLICITAÇÃO DE EXAMES")
        y -= 12 * mm
        c.setFont("Helvetica", 11)
        c.drawString(MARGEM_ESQ, y, f"Paciente: {pedido.paciente}")
        if data:
            c.drawRightString(LARGURA - MARGEM_DIR, y, f"Realizar a partir de: {data}")
        y -= 9 * mm
        if pedido.indicacao:
            y = _paragrafo(c, f"Indicação clínica: {pedido.indicacao}",
                           MARGEM_ESQ, y, LARGURA_UTIL, tamanho=10) - 3 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGEM_ESQ, y, "Solicito:")
        y -= 8 * mm
        for exame in pedido.exames:
            c.setFont("Helvetica", 12)
            c.rect(MARGEM_ESQ, y - 1, 3.6 * mm, 3.6 * mm)   # caixinha p/ marcar no laboratório
            rotulo = exame.nome + (f"  —  {exame.material}" if exame.material else "")
            y = _paragrafo(c, rotulo, MARGEM_ESQ + 7 * mm, y, LARGURA_UTIL - 7 * mm,
                           tamanho=11, entrelinha=4.8 * mm) - 2 * mm
            if y < 80 * mm:
                _assinatura_rodape(c, data=data, carimbo=pedido.carimbo)
                c.showPage()
                _fundo_timbrado(c)
                y = ALTURA - 45 * mm
        if pedido.observacao:
            y -= 2 * mm
            y = _paragrafo(c, f"Obs.: {pedido.observacao}", MARGEM_ESQ, y,
                           LARGURA_UTIL, tamanho=10)
        _assinatura_rodape(c, data=data, carimbo=pedido.carimbo)
        c.showPage()
    c.save()
    return destino
