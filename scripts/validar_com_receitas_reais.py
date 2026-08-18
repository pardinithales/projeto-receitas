"""Validação local: compara o PDF gerado pelo sistema com receitas .docx reais já emitidas.

Sorteia N receitas reais da pasta do consultório, extrai paciente/itens/posologias,
regenera cada uma pelo gerador do sistema e confere que todo o conteúdo bate.
NADA é copiado para o repositório: roda apenas localmente, resultado no terminal.

Uso:  python scripts/validar_com_receitas_reais.py [N]
"""
import random
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.receita_pdf import ItemReceita, Receita, gerar_receita_pdf  # noqa: E402

PASTA_REAL = Path(r"M:\Thales Pardini - Neurologia\Receitas Thales Pardini - Neurologia")
SAIDA = Path(__file__).resolve().parent.parent / "dados" / "validacao"

RE_MED = re.compile(r"^(?P<med>.+?)\s*_{3,}\s*(?P<qtd>.+)$")
RE_PACIENTE = re.compile(r"^\s*paciente\b[:\s]*", re.IGNORECASE)
FIM_ITENS = ("IDENTIFICAÇÃO DO COMPRADOR", "Data:", "____")
# Rótulos do bloco comprador/fornecedor e afins — nunca são medicamentos
RE_NAO_MED = re.compile(
    r"^\s*(nome|ident|endere|cidade|telefone|data|ass|crm|cremesp|dr\.?\b|uf\b)",
    re.IGNORECASE,
)


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().lower()


def parsear_docx(caminho: Path) -> Receita | None:
    doc = Document(caminho)
    linhas = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if not linhas or "RECEITU" not in linhas[0].upper():
        return None
    tipo = "controle_especial" if "CONTROLE" in linhas[0].upper() else "comum"

    paciente, via = "", "USO ORAL"
    itens: list[ItemReceita] = []
    i = 0
    while i < len(linhas):
        ln = linhas[i]
        if "IDENTIFICAÇÃO DO COMPRADOR" in ln.upper():
            break
        if RE_PACIENTE.match(ln) and not paciente:
            paciente = RE_PACIENTE.sub("", ln).strip()
        elif ln.upper().startswith("USO "):
            via = ln
        elif (m := RE_MED.match(ln)) and "IDENTIFICAÇÃO" not in ln.upper() \
                and not RE_NAO_MED.match(m["med"]):
            posologia = []
            j = i + 1
            while j < len(linhas):
                prox = linhas[j]
                if RE_MED.match(prox) or any(prox.startswith(f) for f in FIM_ITENS) \
                        or "IDENTIFICAÇÃO" in prox.upper():
                    break
                posologia.append(prox)
                j += 1
            itens.append(ItemReceita(m["med"].strip(), m["qtd"].strip(),
                                     " ".join(posologia)))
            i = j - 1
        i += 1

    if not paciente or not itens:
        return None
    return Receita(paciente=paciente, itens=itens, tipo=tipo, via_administracao=via)


def texto_pdf(caminho: Path) -> str:
    with pdfplumber.open(caminho) as pdf:
        return " ".join((p.extract_text() or "").replace("\n", " ") for p in pdf.pages)


def validar(caminho: Path, n_arquivo: int) -> tuple[bool, list[str]]:
    receita = parsear_docx(caminho)
    if receita is None:
        return True, ["ignorado (não é receita ou sem itens parseáveis)"]
    pdf = gerar_receita_pdf(receita, SAIDA / f"validacao_{n_arquivo}.pdf")
    texto = normalizar(texto_pdf(pdf))
    falhas = []
    for esperado in [receita.paciente] + \
            [x for it in receita.itens for x in (it.medicamento, it.quantidade)]:
        if normalizar(esperado) not in texto:
            falhas.append(f"faltou: {esperado!r}")
    for it in receita.itens:
        if it.posologia and normalizar(it.posologia)[:30] not in texto:
            falhas.append(f"posologia divergente: {it.posologia[:50]!r}")
    return not falhas, falhas or ["ok"]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    docs = [p for p in PASTA_REAL.rglob("*.docx") if not p.name.startswith("~$")]
    amostra = random.sample(docs, min(n * 3, len(docs)))  # 3x: parte não é receita
    testados = aprovados = 0
    for arq in amostra:
        if testados >= n:
            break
        try:
            receita = parsear_docx(arq)
        except Exception as e:
            print(f"  ERRO lendo {arq.name[:60]}: {e}")
            continue
        if receita is None:
            continue
        testados += 1
        ok, detalhes = validar(arq, testados)
        status = "OK " if ok else "DIVERGIU"
        aprovados += ok
        print(f"[{status}] ({len(receita.itens)} itens) {arq.name[:70]}")
        if not ok:
            for d in detalhes:
                print(f"        - {d}")
    print(f"\n{aprovados}/{testados} receitas reais reproduzidas fielmente.")
    print(f"PDFs de conferência visual em: {SAIDA}")


if __name__ == "__main__":
    main()
