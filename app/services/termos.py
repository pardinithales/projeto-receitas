"""Termos de Esclarecimento e Responsabilidade (TER/TCLE) preenchidos.

O TER de anticonvulsivantes (CEAF) é um AcroForm que já contém o carimbo do
médico embutido: preenchemos nome, CNS, data e marcamos o(s) medicamento(s).
Demais termos: copiados como estão (preenchimento específico é evolução futura).
"""
from pathlib import Path

import pikepdf

from app import config

TER_EPILEPSIA = (config.TERMOS_DIR /
                 "AAAAA - TERMO_EPILEPSIA_MAIS_NOVO_LEVETIRACETAM - final - MARCAVEL.pdf")

# Ordem dos checkboxes de medicamento na página 2 do TER (de cima para baixo)
MEDS_TER_EPILEPSIA = ["ácido valproico", "carbamazepina", "clobazam", "clonazepam",
                      "etossuximida", "fenitoína", "fenobarbital", "gabapentina",
                      "lamotrigina", "levetiracetam", "primidona", "topiramato",
                      "vigabatrina"]

OUTROS_TERMOS = {
    "piridostigmina": "aaaaaaaaa - TCLE piridostigmina mestinom azatioprina.pdf",
    "azatioprina": "aaaaaaaaa - TCLE piridostigmina mestinom azatioprina.pdf",
    "imunoglobulina": "AAAAAAAAAAAA TCLE TERMOS GUILLAIN BARRE IVIG.pdf",
    "gabapentina_dor": "aaaaaaaaaaaaaa TERMO CONSENTIMENTO GABAPENTINA DOR CRONICA.pdf",
    "toxina": "MELHOR TERMO TCLE CONSENTIMENTO BOTOX TOXINA BOTULINICA.pdf",
    "demencia": "termo_lme_donepezila_galantamina_rivastigmina_cdr_mini_mental_meem_PERFEITO_MELHOR.pdf",
}


def _normalizar(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def termo_para_medicamentos(medicamentos: list[str]) -> str | None:
    """Escolhe o termo certo pela lista de medicamentos do LME."""
    texto = _normalizar(" ".join(medicamentos))
    for med in MEDS_TER_EPILEPSIA:
        if _normalizar(med).split()[0] in texto:
            return "epilepsia"
    for chave in OUTROS_TERMOS:
        if chave.split("_")[0] in texto:
            return chave
    if "botox" in texto or "botul" in texto:
        return "toxina"
    for demencia_med in ("donepezila", "rivastigmina", "galantamina", "memantina"):
        if demencia_med in texto:
            return "demencia"
    return None


def gerar_termo(tipo: str, destino: Path, paciente: str = "", cns: str = "",
                medicamentos: list[str] | None = None, data: str = "") -> Path | None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if tipo == "epilepsia":
        return _preencher_ter_epilepsia(destino, paciente, cns,
                                        medicamentos or [], data)
    arquivo = OUTROS_TERMOS.get(tipo)
    if not arquivo:
        return None
    origem = config.TERMOS_DIR / arquivo
    if not origem.exists():
        return None
    destino.write_bytes(origem.read_bytes())
    return destino


def _carimbar_pagina(pdf: pikepdf.Pdf, pagina, x: float, y: float,
                     largura: float = 88) -> None:
    """Desenha o carimbo como conteúdo da página (sai em qualquer leitor)."""
    import io

    from reportlab.pdfgen.canvas import Canvas as RLCanvas

    if not config.CARIMBO_PATH.exists():
        return
    box = [float(v) for v in pagina.MediaBox]
    buf = io.BytesIO()
    c = RLCanvas(buf, pagesize=(box[2], box[3]))
    c.drawImage(str(config.CARIMBO_PATH), x, y, width=largura,
                height=largura * 184 / 271, mask="auto")
    c.showPage()
    c.save()
    buf.seek(0)
    overlay = pikepdf.open(buf)
    pagina.add_overlay(overlay.pages[0])


def _preencher_ter_epilepsia(destino: Path, paciente: str, cns: str,
                             medicamentos: list[str], data: str) -> Path | None:
    if not TER_EPILEPSIA.exists():
        return None
    pdf = pikepdf.open(TER_EPILEPSIA)
    pdf.Root.AcroForm.NeedAppearances = True

    quer = {_normalizar(m).split()[0] for m in medicamentos}
    indices = {i for i, nome in enumerate(MEDS_TER_EPILEPSIA)
               if _normalizar(nome).split()[0] in quer}

    idx_btn = 0
    for page in pdf.pages:
        for annot in page.get("/Annots", []) or []:
            t = annot.get("/T")
            ft = str(annot.get("/FT", ""))
            if t is None:
                continue
            nome = str(t)
            if ft == "/Tx":
                valor = None
                if nome == "Eu" or nome == "Nome do paciente":
                    valor = paciente
                elif "Cart" in nome:
                    valor = cns
                elif nome == "Data":
                    valor = data
                elif nome.startswith(("Nome do respons", "Documento", "Assinatura")):
                    valor = " "     # limpa resíduos do arquivo-modelo
                if valor is not None:
                    annot.V = pikepdf.String(valor)
                    if "/AP" in annot:
                        del annot["/AP"]
            elif ft == "/Btn":
                # checkboxes na ordem visual; nomes se repetem, então usamos a posição
                annot.V = pikepdf.Name("/Sim" if idx_btn in indices else "/Off")
                annot.AS = pikepdf.Name("/Sim" if idx_btn in indices else "/Off")
                idx_btn += 1
    # carimbo sobre a linha "Assinatura e carimbo do médico" (acima do campo Data,
    # que fica em Rect ~[251,253,371,269] na última página)
    _carimbar_pagina(pdf, pdf.pages[-1], x=265, y=278)
    pdf.save(destino)
    return destino
