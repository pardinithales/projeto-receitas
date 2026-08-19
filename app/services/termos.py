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


def termo_para_medicamentos(medicamentos: list[str], cid10: str = "") -> str | None:
    """Escolhe o termo certo pela lista de medicamentos E pela indicação (CID).
    Ex.: gabapentina com R52 (dor) usa o termo de dor crônica, não o de epilepsia."""
    texto = _normalizar(" ".join(medicamentos))
    cid = cid10.upper()
    if cid.startswith("R52") and "gabapentina" in texto:
        return "gabapentina_dor"
    if cid.startswith(("G30", "F00")):
        return "demencia"
    if cid.startswith("G40"):
        for med in MEDS_TER_EPILEPSIA:
            if _normalizar(med).split()[0] in texto:
                return "epilepsia"
    if not cid:    # sem CID: cai na heurística por medicamento
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
                medicamentos: list[str] | None = None, data: str = "",
                meem: str = "", cdr: str = "", escolaridade: str = "") -> Path | None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if tipo == "epilepsia":
        return _preencher_ter_epilepsia(destino, paciente, cns,
                                        medicamentos or [], data)
    if tipo == "demencia":
        return _preencher_termo_demencia(destino, medicamentos or [], data,
                                         meem, cdr, escolaridade)
    arquivo = OUTROS_TERMOS.get(tipo)
    if not arquivo:
        return None
    origem = config.TERMOS_DIR / arquivo
    if not origem.exists():
        return None
    # cópia com carimbo nas âncoras de assinatura (dinâmico por termo)
    pdf = pikepdf.open(origem)
    for pg_i, x, y in _ancoras_assinatura(origem):
        _carimbar_pagina(pdf, pdf.pages[pg_i], x=x, y=y, largura=80)
    pdf.save(destino)
    return destino


def _ancoras_assinatura(caminho: Path) -> list[tuple[int, float, float]]:
    """Localiza as linhas de 'Assinatura' de cada página para carimbar em cima."""
    import pdfplumber
    ancoras = []
    try:
        with pdfplumber.open(caminho) as pdf:
            for i, pg in enumerate(pdf.pages):
                for w in pg.extract_words():
                    if "ssinatura" in w["text"]:
                        ancoras.append((i, w["x1"] + 30, pg.height - w["bottom"] + 4))
                        break     # 1 carimbo por página basta
    except Exception:
        pass
    return ancoras


# Campos do MEEM embutido no termo de demência (página 3) e máximos por domínio.
# Ordem de perda típica na doença de Alzheimer, usada para distribuir o total
# quando só o escore global foi informado (sempre conferir antes de assinar).
MEEM_DOMINIOS = [
    ("3_2", 3),    # evocação das 3 palavras
    ("5", 5),      # orientação temporal
    ("5_3", 5),    # atenção e cálculo
    ("5_2", 5),    # orientação espacial
    ("1_4", 1),    # cópia do desenho
    ("3_3", 3),    # comando de 3 etapas
    ("1_3", 1),    # escrever frase
    ("2", 2),      # nomeação
    ("1", 1),      # repetição
    ("1_2", 1),    # leitura
    ("3", 3),      # memória imediata
]


def _distribuir_meem(total: int) -> dict[str, int]:
    """Distribui o escore total pelos domínios (perde primeiro evocação,
    orientação e cálculo — padrão típico de DA)."""
    deficit = max(0, 30 - total)
    valores = {}
    for campo, maximo in MEEM_DOMINIOS:
        perde = min(maximo, deficit)
        valores[campo] = maximo - perde
        deficit -= perde
    return valores


def _preencher_termo_demencia(destino: Path, medicamentos: list[str], data: str,
                              meem: str, cdr: str, escolaridade: str) -> Path | None:
    origem = config.TERMOS_DIR / OUTROS_TERMOS["demencia"]
    if not origem.exists():
        return None
    pdf = pikepdf.open(origem)
    pdf.Root.AcroForm.NeedAppearances = True
    texto_meds = _normalizar(" ".join(medicamentos))
    try:
        valores_meem = _distribuir_meem(int(float(meem))) if meem else {}
    except ValueError:
        valores_meem = {}

    for page in pdf.pages:
        for annot in page.get("/Annots", []) or []:
            t = annot.get("/T")
            if t is None:
                continue
            nome = str(t)
            ft = str(annot.get("/FT", ""))
            if ft == "/Btn":       # checkbox do medicamento (Donepezila etc.)
                marcado = _normalizar(nome) in texto_meds
                estado = "/Off"
                ap = annot.get("/AP")
                if marcado and ap is not None and ap.get("/N") is not None:
                    estados = [str(s) for s in ap.get("/N").keys() if str(s) != "/Off"]
                    estado = estados[0] if estados else "/Off"
                annot.V = pikepdf.Name(estado)
                annot.AS = pikepdf.Name(estado)
            elif ft == "/Tx":
                valor = None
                if nome.startswith("Escolaridade"):
                    valor = escolaridade
                elif nome == "30":
                    valor = meem
                elif nome.startswith("Escore final"):
                    valor = f"CDR {cdr}" if cdr else ""
                elif nome in valores_meem:
                    valor = str(valores_meem[nome])
                if valor:
                    annot.V = pikepdf.String(valor)
                    if "/AP" in annot:
                        del annot["/AP"]

    # Local/Data (texto plano na pág. 2) + carimbos nas 3 páginas com assinatura
    import io

    from reportlab.pdfgen.canvas import Canvas as RLCanvas
    box = [float(v) for v in pdf.pages[1].MediaBox]
    buf = io.BytesIO()
    c = RLCanvas(buf, pagesize=(box[2], box[3]))
    c.setFont("Helvetica", 10)
    c.drawString(125, 750, config.CIDADE_PADRAO)
    c.drawString(372, 750, data)
    c.save()
    buf.seek(0)
    overlay_local_data = pikepdf.open(buf)
    pdf.pages[1].add_overlay(overlay_local_data.pages[0])
    _carimbar_pagina(pdf, pdf.pages[1], x=230, y=598, largura=85)   # méd. pg2
    _carimbar_pagina(pdf, pdf.pages[2], x=200, y=78, largura=80)    # MEEM pg3
    _carimbar_pagina(pdf, pdf.pages[4], x=200, y=140, largura=80)   # CDR/final pg5
    pdf.save(destino)
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
    # carimbo sobre a linha de assinatura do médico (faixa livre y~285-318, medida
    # da página; fundo do carimbo é transparente, então pode encostar nos textos)
    _carimbar_pagina(pdf, pdf.pages[-1], x=255, y=272, largura=80)
    pdf.save(destino)
    return destino
