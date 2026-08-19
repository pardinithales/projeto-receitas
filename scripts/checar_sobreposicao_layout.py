"""Detector de sobreposição de texto nos PDFs gerados — SÓ dados fictícios.

Gera cenários de texto LONGO em todos os geradores e verifica, por caixas de
palavras (pdfplumber), que nada sobrepõe assinatura/carimbo. Rodar após
qualquer mudança de layout:

    python scripts/checar_sobreposicao_layout.py           # só checa
    python scripts/checar_sobreposicao_layout.py render    # + PNGs por página

Saída em dados/checagem-layout/ (fora do git).
"""
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.documentos_pdf import (Atestado, Encaminhamento, PedidoExames,
                                         ExameSolicitado, RelatorioMedico,
                                         RelatorioPrevidenciario,
                                         gerar_atestado_pdf,
                                         gerar_encaminhamento_pdf,
                                         gerar_pedido_exames_pdf,
                                         gerar_relatorio_pdf,
                                         gerar_relatorio_previdenciario_pdf)
from app.services.receita_pdf import ItemReceita, Receita, gerar_receita_pdf

SAIDA = Path(__file__).resolve().parents[1] / "dados" / "checagem-layout"
SAIDA.mkdir(parents=True, exist_ok=True)

LONGO = "\n\n".join(
    f"Tópico {i}: paciente com quadro clínico extenso, em investigação "
    "neurológica prolongada, com múltiplos exames e avaliações seriadas "
    "documentadas ao longo do seguimento ambulatorial." for i in range(28))


def checar(caminho: Path) -> tuple[list[str], int]:
    """Pares de palavras com caixas sobrepostas (ignora linhas de assinatura)."""
    problemas = []
    with pdfplumber.open(caminho) as pdf:
        for num, pagina in enumerate(pdf.pages, 1):
            palavras = [w for w in pagina.extract_words()
                        if set(w["text"]) != {"_"}]
            for i, a in enumerate(palavras):
                for b in palavras[i + 1:]:
                    if (a["x0"] < b["x1"] - 1 and b["x0"] < a["x1"] - 1
                            and a["top"] < b["bottom"] - 1.5
                            and b["top"] < a["bottom"] - 1.5):
                        problemas.append(
                            f"  p{num}: '{a['text']}' × '{b['text']}' "
                            f"(y {a['top']:.0f}/{b['top']:.0f})")
        return problemas, len(pdf.pages)


def render(caminho: Path) -> None:
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(caminho))
    for i, pagina in enumerate(doc):
        pagina.render(scale=1.4).to_pil().save(
            SAIDA / f"{caminho.stem}_p{i + 1}.png")


def main() -> None:
    docs = {}
    docs["encaminhamento"] = gerar_encaminhamento_pdf(Encaminhamento(
        paciente="Maria Exemplo da Silva", especialidades=["Neurocirurgia"],
        destino="", motivo=LONGO, cid10="G40.1", data="19/08/2026",
        carimbo=True), SAIDA / "encaminhamento_longo.pdf")
    docs["carta"] = gerar_encaminhamento_pdf(Encaminhamento(
        paciente="Maria Exemplo da Silva", especialidades=[],
        destino="UPA Central", titulo="RESPOSTA — CONTRARREFERÊNCIA",
        motivo=LONGO, data="19/08/2026", carimbo=True),
        SAIDA / "carta_longa.pdf")
    docs["relatorio"] = gerar_relatorio_pdf(RelatorioMedico(
        paciente="Maria Exemplo da Silva", texto=LONGO, cid10="G40.1",
        data="19/08/2026", carimbo=True), SAIDA / "relatorio_longo.pdf")
    docs["atestado"] = gerar_atestado_pdf(Atestado(
        paciente="Maria Exemplo da Silva", texto=LONGO, cid10="G40.1",
        data="19/08/2026", carimbo=True), SAIDA / "atestado_longo.pdf")
    docs["previdenciario"] = gerar_relatorio_previdenciario_pdf(
        RelatorioPrevidenciario(paciente="Maria Exemplo da Silva", texto=LONGO,
                                cids=["G40.1 - Epilepsia"], data="19/08/2026",
                                documento="12.345.678-9", carimbo=True),
        SAIDA / "previdenciario_longo.pdf")
    docs["exames"] = gerar_pedido_exames_pdf(PedidoExames(
        paciente="Maria Exemplo da Silva",
        exames=[ExameSolicitado(f"Exame de rotina número {i} com nome bem "
                                "comprido para forçar quebra", "sangue")
                for i in range(28)],
        indicacao="Seguimento.", datas=["19/08/2026"], carimbo=True),
        SAIDA / "exames_longo.pdf")
    itens = [ItemReceita(
        f"Medicamento Exemplo {i} 500mg - comprimido", "30 comprimidos",
        "Tomar 1 comprimido pela manhã durante 7 dias;\n"
        "Após, tomar 1 comprimido de 12 em 12 horas por 2 semanas;\n"
        "Após, tomar 2 comprimidos de 12 em 12 horas, uso contínuo.")
        for i in range(6)]
    docs["receita"] = gerar_receita_pdf(Receita(
        paciente="Maria Exemplo da Silva", itens=itens, data="19/08/2026",
        vias=1, carimbo=True, uso_continuo=True), SAIDA / "receita_longa.pdf")
    docs["receita_pos_gigante"] = gerar_receita_pdf(Receita(
        paciente="Maria Exemplo da Silva",
        itens=[ItemReceita("Vitamina B12 5000mcg - ampola IM", "16 ampolas",
                           LONGO)],
        vias=2, carimbo=True), SAIDA / "receita_pos_gigante.pdf")

    todos_ok = True
    for nome, caminho in docs.items():
        problemas, paginas = checar(caminho)
        print(f"{'OK ' if not problemas else 'SOBREPOSIÇÃO'} {nome}: "
              f"{paginas} pág.")
        for p in problemas[:12]:
            print(p)
        todos_ok = todos_ok and not problemas
        if "render" in sys.argv:
            render(caminho)
    print("TUDO OK" if todos_ok else "HÁ PROBLEMAS")
    sys.exit(0 if todos_ok else 1)


if __name__ == "__main__":
    main()
