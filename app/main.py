"""App web local do sistema de receitas. Rodar: uvicorn app.main:app --reload"""
import json
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config, db
from app.services.documentos_pdf import (ExameSolicitado, PedidoExames,
                                         RelatorioMedico, gerar_pedido_exames_pdf,
                                         gerar_relatorio_pdf)
from app.services.lme import DadosLME, MedicamentoLME, preencher_lme
from app.services.receita_pdf import ItemReceita, Receita, gerar_receita_pdf

app = FastAPI(title="Sistema de Receitas")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.on_event("startup")
def startup() -> None:
    db.iniciar_banco()
    db.backup_banco()


# ---------------------------------------------------------------- home / busca

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    con = db.conectar()
    try:
        recentes = con.execute(
            "SELECT d.id, d.tipo, d.data_emissao, p.nome, p.id AS paciente_id "
            "FROM documentos d JOIN pacientes p ON p.id = d.paciente_id "
            "ORDER BY d.id DESC LIMIT 10"
        ).fetchall()
    finally:
        con.close()
    return templates.TemplateResponse(request, "index.html", {"recentes": recentes})


@app.get("/pacientes/busca", response_class=HTMLResponse)
def buscar_pacientes(request: Request, q: str = ""):
    linhas = []
    if len(q.strip()) >= 2:
        con = db.conectar()
        try:
            linhas = con.execute(
                "SELECT id, nome, data_nascimento, tags FROM pacientes "
                "WHERE nome LIKE ? OR tags LIKE ? ORDER BY nome LIMIT 12",
                (f"%{q.strip()}%", f"%{q.strip()}%"),
            ).fetchall()
        finally:
            con.close()
    return templates.TemplateResponse(request, "_lista_pacientes.html",
                                      {"pacientes": linhas, "q": q})


# ---------------------------------------------------------------- pacientes

CAMPOS_PACIENTE = ["nome", "data_nascimento", "cpf", "cns", "rg", "nome_mae",
                   "peso_kg", "altura_cm", "telefone", "endereco", "cidade", "uf",
                   "raca_cor", "tags"]


@app.get("/pacientes/novo", response_class=HTMLResponse)
def novo_paciente(request: Request, nome: str = ""):
    return templates.TemplateResponse(request, "paciente_form.html",
                                      {"paciente": {"nome": nome}, "editar": False})


def _normalizar_nome(nome: str) -> str:
    """Nome canônico: espaços colapsados e Título Por Palavra (preposições minúsculas)."""
    menores = {"da", "de", "do", "das", "dos", "e"}
    palavras = nome.strip().split()
    return " ".join(p.lower() if p.lower() in menores and i > 0 else p.capitalize()
                    for i, p in enumerate(palavras))


def _chave_busca(nome: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", nome)
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).lower().split())


@app.post("/pacientes")
async def criar_paciente(request: Request):
    form = dict(await request.form())
    form["nome"] = _normalizar_nome(form.get("nome", ""))
    valores = [form.get(c) or None for c in CAMPOS_PACIENTE]
    con = db.conectar()
    try:
        # anti-duplicata: mesmo nome ignorando acentos, caixa e espaços extras
        chave = _chave_busca(form["nome"])
        for row in con.execute("SELECT id, nome FROM pacientes"):
            if _chave_busca(row["nome"]) == chave:
                return RedirectResponse(f"/pacientes/{row['id']}", status_code=303)
        cur = con.execute(
            f"INSERT INTO pacientes ({', '.join(CAMPOS_PACIENTE)}, criado_em, atualizado_em) "
            f"VALUES ({', '.join('?' * len(CAMPOS_PACIENTE))}, ?, ?)",
            (*valores, db.agora(), db.agora()),
        )
        con.commit()
        pid = cur.lastrowid
    finally:
        con.close()
    return RedirectResponse(f"/pacientes/{pid}", status_code=303)


@app.get("/pacientes/{pid}/editar", response_class=HTMLResponse)
def editar_paciente(request: Request, pid: int):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
    finally:
        con.close()
    return templates.TemplateResponse(request, "paciente_form.html",
                                      {"paciente": paciente, "editar": True})


@app.post("/pacientes/{pid}/editar")
async def salvar_paciente(request: Request, pid: int):
    form = dict(await request.form())
    valores = [form.get(c) or None for c in CAMPOS_PACIENTE]
    con = db.conectar()
    try:
        con.execute(
            f"UPDATE pacientes SET {', '.join(c + ' = ?' for c in CAMPOS_PACIENTE)}, "
            "atualizado_em = ? WHERE id = ?",
            (*valores, db.agora(), pid),
        )
        con.commit()
    finally:
        con.close()
    return RedirectResponse(f"/pacientes/{pid}", status_code=303)


@app.get("/pacientes/{pid}", response_class=HTMLResponse)
def ver_paciente(request: Request, pid: int):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        documentos = con.execute(
            "SELECT id, tipo, data_emissao, conteudo_json, caminho_pdf FROM documentos "
            "WHERE paciente_id = ? ORDER BY id DESC LIMIT 30", (pid,)
        ).fetchall()
    finally:
        con.close()
    docs = [dict(d) | {"resumo": _resumo_documento(d)} for d in documentos]
    return templates.TemplateResponse(request, "paciente.html",
                                      {"paciente": paciente, "documentos": docs})


def _resumo_documento(doc) -> str:
    try:
        payload = json.loads(doc["conteudo_json"])
        meds = [i["medicamento"].split(" ")[0] for i in payload.get("itens", [])]
        return ", ".join(meds[:4])
    except Exception:
        return ""


# ---------------------------------------------------------------- catálogo

@app.get("/api/catalogo")
def catalogo():
    con = db.conectar()
    try:
        meds = con.execute("SELECT * FROM medicamentos ORDER BY principio_ativo").fetchall()
        aprs = con.execute("SELECT * FROM apresentacoes").fetchall()
        poss = con.execute("SELECT * FROM posologias").fetchall()
    finally:
        con.close()
    por_apr: dict[int, list] = {}
    for p in poss:
        por_apr.setdefault(p["apresentacao_id"], []).append(
            {"texto": p["texto"], "qtd_30dias": p["qtd_30dias"]})
    por_med: dict[int, list] = {}
    for a in aprs:
        por_med.setdefault(a["medicamento_id"], []).append(
            {"dose": a["dose"], "forma": a["forma"],
             "posologias": por_apr.get(a["id"], [])})
    return [
        {"id": m["id"], "principio_ativo": m["principio_ativo"],
         "classificacao": m["classificacao_receita"],
         "disponibilidade": json.loads(m["disponibilidade"]),
         "lme": bool(m["lme"]), "obs": m["obs"],
         "apresentacoes": por_med.get(m["id"], [])}
        for m in meds
    ]


# ---------------------------------------------------------------- receita

@app.get("/pacientes/{pid}/receita", response_class=HTMLResponse)
def form_receita(request: Request, pid: int, copiar_de: int | None = None):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        payload_anterior = None
        if copiar_de:
            doc = con.execute(
                "SELECT conteudo_json FROM documentos WHERE id = ? AND paciente_id = ?",
                (copiar_de, pid)).fetchone()
            if doc:
                payload_anterior = doc["conteudo_json"]
    finally:
        con.close()
    return templates.TemplateResponse(request, "receita_form.html", {
        "paciente": paciente,
        "payload_anterior": payload_anterior,
        "hoje": date.today().strftime("%d/%m/%Y"),
    })


@app.post("/pacientes/{pid}/receita")
def emitir_receita(pid: int,
                   tipo: str = Form("controle_especial"),
                   via_administracao: str = Form("USO ORAL"),
                   com_data: str = Form("sem"),
                   acao: str = Form("gerar"),
                   vias: int = Form(1),
                   itens_json: str = Form(...)):
    itens_raw = json.loads(itens_json)
    if not itens_raw:
        return RedirectResponse(f"/pacientes/{pid}/receita", status_code=303)
    payload = {"tipo": tipo, "via_administracao": via_administracao,
               "com_data": com_data, "vias": vias, "itens": itens_raw}
    con = db.conectar()
    try:
        cur = con.execute(
            "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
            "VALUES (?, ?, ?, ?)",
            (pid, f"receita_{tipo}", db.agora(), json.dumps(payload, ensure_ascii=False)),
        )
        doc_id = cur.lastrowid
        if acao == "gerar":
            _gerar_pdf_receita(con, doc_id)
        con.commit()
    finally:
        con.close()
    if acao == "gerar":
        return RedirectResponse(f"/documentos/{doc_id}/pdf", status_code=303)
    return RedirectResponse(f"/pacientes/{pid}", status_code=303)


def _gerar_pdf_receita(con, doc_id: int) -> str:
    """Gera (ou regenera) o PDF de um documento salvo; retorna o caminho."""
    doc = con.execute("SELECT * FROM documentos WHERE id = ?", (doc_id,)).fetchone()
    paciente = con.execute("SELECT * FROM pacientes WHERE id = ?",
                           (doc["paciente_id"],)).fetchone()
    payload = json.loads(doc["conteudo_json"])
    data_txt = ""
    if payload.get("com_data") == "com":
        data_txt = datetime.fromisoformat(doc["data_emissao"]).strftime("%d/%m/%Y")
    receita = Receita(
        paciente=paciente["nome"],
        itens=[ItemReceita(i["medicamento"], i["quantidade"], i["posologia"])
               for i in payload["itens"]],
        tipo=payload.get("tipo", "controle_especial"),
        via_administracao=payload.get("via_administracao", "USO ORAL"),
        data=data_txt,
        vias=int(payload.get("vias", 1)),
    )
    nome_arq = f"{doc_id:05d}_receita_{datetime.now():%Y%m%d}.pdf"
    destino = config.SAIDA_DIR / f"paciente_{paciente['id']}" / nome_arq
    gerar_receita_pdf(receita, destino)
    con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                (str(destino), doc_id))
    return str(destino)


# ---------------------------------------------------------------- LME

CAMPOS_LME_PACIENTE = {"nome_mae": "nome da mãe", "peso_kg": "peso",
                       "altura_cm": "altura"}


@app.get("/pacientes/{pid}/lme", response_class=HTMLResponse)
def form_lme(request: Request, pid: int):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        lme = con.execute("SELECT * FROM lme_dados WHERE paciente_id = ?", (pid,)).fetchone()
    finally:
        con.close()
    return templates.TemplateResponse(request, "lme_form.html", {
        "paciente": paciente,
        "lme": dict(lme) if lme else {},
        "hoje": date.today().strftime("%d/%m/%Y"),
    })


@app.post("/pacientes/{pid}/lme")
async def emitir_lme(request: Request, pid: int):
    form = dict(await request.form())
    meds_raw = json.loads(form.get("meds_json") or "[]")
    con = db.conectar()
    try:
        paciente = dict(con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone())

        # dados do paciente editáveis na própria tela do LME
        for campo in ("nome_mae", "peso_kg", "altura_cm", "cpf", "cns", "raca_cor",
                      "telefone"):
            if form.get(campo):
                paciente[campo] = form[campo]
        con.execute(
            "UPDATE pacientes SET nome_mae = ?, peso_kg = ?, altura_cm = ?, cpf = ?, "
            "cns = ?, raca_cor = ?, telefone = ?, atualizado_em = ? WHERE id = ?",
            (paciente.get("nome_mae"), paciente.get("peso_kg"), paciente.get("altura_cm"),
             paciente.get("cpf"), paciente.get("cns"), paciente.get("raca_cor"),
             paciente.get("telefone"), db.agora(), pid))

        # dados clínicos do LME ficam salvos para a renovação semestral
        con.execute("INSERT INTO lme_dados (paciente_id, cid10, diagnostico, anamnese, "
                    "tratamentos_previos, incapaz, nome_responsavel, atualizado_em) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(paciente_id) DO UPDATE SET cid10 = excluded.cid10, "
                    "diagnostico = excluded.diagnostico, anamnese = excluded.anamnese, "
                    "tratamentos_previos = excluded.tratamentos_previos, "
                    "incapaz = excluded.incapaz, nome_responsavel = excluded.nome_responsavel, "
                    "atualizado_em = excluded.atualizado_em",
                    (pid, form.get("cid10"), form.get("diagnostico"), form.get("anamnese"),
                     form.get("tratamentos_previos"),
                     1 if form.get("incapaz") == "sim" else 0,
                     form.get("nome_responsavel"), db.agora()))

        # validação dos obrigatórios do formulário oficial
        faltando = [rotulo for campo, rotulo in CAMPOS_LME_PACIENTE.items()
                    if not paciente.get(campo)]
        for campo, rotulo in (("cid10", "CID-10"), ("diagnostico", "diagnóstico"),
                              ("anamnese", "anamnese")):
            if not form.get(campo):
                faltando.append(rotulo)
        if not meds_raw:
            faltando.append("ao menos 1 medicamento")
        if faltando:
            con.commit()   # preserva o que já foi preenchido
            lme = con.execute("SELECT * FROM lme_dados WHERE paciente_id = ?",
                              (pid,)).fetchone()
            return templates.TemplateResponse(request, "lme_form.html", {
                "paciente": paciente, "lme": dict(lme) if lme else {},
                "hoje": date.today().strftime("%d/%m/%Y"),
                "erro": "Faltam campos obrigatórios do LME: " + ", ".join(faltando),
            }, status_code=422)

        documento_tipo = "CNS" if paciente.get("cns") else ("CPF" if paciente.get("cpf") else "")
        dados = DadosLME(
            paciente=paciente["nome"].upper(),
            nome_mae=(paciente.get("nome_mae") or "").upper(),
            peso_kg=str(paciente.get("peso_kg") or ""),
            altura_cm=str(paciente.get("altura_cm") or ""),
            medicamentos=[MedicamentoLME(m["descricao"], [m["qtd_mensal"]] * 6)
                          for m in meds_raw],
            cid10=(form.get("cid10") or "").upper(),
            diagnostico=form.get("diagnostico") or "",
            anamnese=form.get("anamnese") or "",
            tratamentos_previos=form.get("tratamentos_previos") or "",
            incapaz=form.get("incapaz") == "sim",
            nome_responsavel=form.get("nome_responsavel") or "",
            raca_cor=paciente.get("raca_cor") or "",
            telefone=paciente.get("telefone") or "",
            documento_tipo=documento_tipo,
            documento_numero=paciente.get("cns") or paciente.get("cpf") or "",
            data=date.today().strftime("%d/%m/%Y") if form.get("com_data") == "com" else "",
        )
        payload = {"meds": meds_raw, "cid10": dados.cid10,
                   "com_data": form.get("com_data", "sem"),
                   "relatorio": form.get("gerar_relatorio") == "sim"}
        cur = con.execute(
            "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
            "VALUES (?, 'lme', ?, ?)",
            (pid, db.agora(), json.dumps(payload, ensure_ascii=False)))
        doc_id = cur.lastrowid
        destino = config.SAIDA_DIR / f"paciente_{pid}" / \
            f"{doc_id:05d}_lme_{datetime.now():%Y%m%d}.pdf"
        preencher_lme(dados, destino)
        con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                    (str(destino), doc_id))

        if form.get("gerar_relatorio") == "sim":
            texto_rel = form.get("texto_relatorio") or ""
            rel = RelatorioMedico(paciente=paciente["nome"], texto=texto_rel,
                                  cid10=dados.cid10,
                                  data=date.today().strftime("%d/%m/%Y"))
            cur2 = con.execute(
                "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
                "VALUES (?, 'relatorio_alto_custo', ?, ?)",
                (pid, db.agora(), json.dumps({"texto": texto_rel, "cid10": dados.cid10},
                                             ensure_ascii=False)))
            destino_rel = config.SAIDA_DIR / f"paciente_{pid}" / \
                f"{cur2.lastrowid:05d}_relatorio_{datetime.now():%Y%m%d}.pdf"
            gerar_relatorio_pdf(rel, destino_rel)
            con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                        (str(destino_rel), cur2.lastrowid))
        con.commit()
    finally:
        con.close()
    return RedirectResponse(f"/documentos/{doc_id}/pdf", status_code=303)


# ---------------------------------------------------------------- pedido de exames

@app.get("/api/paineis-exames")
def paineis_exames():
    seed = json.loads((config.SEEDS_DIR / "exames_monitoramento.json")
                      .read_text(encoding="utf-8"))
    return seed["paineis"]


@app.get("/pacientes/{pid}/exames", response_class=HTMLResponse)
def form_exames(request: Request, pid: int):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        lme = con.execute("SELECT cid10 FROM lme_dados WHERE paciente_id = ?",
                          (pid,)).fetchone()
    finally:
        con.close()
    return templates.TemplateResponse(request, "exames_form.html", {
        "paciente": paciente,
        "cid10": lme["cid10"] if lme else "",
        "hoje": date.today().strftime("%d/%m/%Y"),
    })


def _somar_meses(base: date, meses: int) -> date:
    mes = base.month - 1 + meses
    ano = base.year + mes // 12
    mes = mes % 12 + 1
    dia = min(base.day, [31, 29 if ano % 4 == 0 else 28, 31, 30, 31, 30,
                         31, 31, 30, 31, 30, 31][mes - 1])
    return date(ano, mes, dia)


@app.post("/pacientes/{pid}/exames")
async def emitir_exames(request: Request, pid: int):
    form = dict(await request.form())
    exames_raw = json.loads(form.get("exames_json") or "[]")
    if not exames_raw:
        return RedirectResponse(f"/pacientes/{pid}/exames", status_code=303)
    meses = [int(m) for m in json.loads(form.get("meses_json") or "[0]")]
    datas = [_somar_meses(date.today(), m).strftime("%d/%m/%Y") for m in sorted(meses)] \
        if form.get("com_data", "com") == "com" else [""] * max(1, len(meses))
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        pedido = PedidoExames(
            paciente=paciente["nome"],
            exames=[ExameSolicitado(e["nome"], e.get("material", "")) for e in exames_raw],
            indicacao=form.get("indicacao") or "",
            datas=datas,
        )
        payload = {"exames": exames_raw, "meses": meses,
                   "indicacao": pedido.indicacao, "com_data": form.get("com_data", "com")}
        cur = con.execute(
            "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
            "VALUES (?, 'pedido_exames', ?, ?)",
            (pid, db.agora(), json.dumps(payload, ensure_ascii=False)))
        doc_id = cur.lastrowid
        destino = config.SAIDA_DIR / f"paciente_{pid}" / \
            f"{doc_id:05d}_exames_{datetime.now():%Y%m%d}.pdf"
        gerar_pedido_exames_pdf(pedido, destino)
        con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                    (str(destino), doc_id))
        con.commit()
    finally:
        con.close()
    return RedirectResponse(f"/documentos/{doc_id}/pdf", status_code=303)


@app.get("/documentos/{doc_id}/pdf")
def abrir_pdf(doc_id: int):
    con = db.conectar()
    try:
        doc = con.execute("SELECT caminho_pdf FROM documentos WHERE id = ?",
                          (doc_id,)).fetchone()
        if not doc:
            return HTMLResponse("Documento não encontrado", status_code=404)
        caminho = doc["caminho_pdf"]
        if not caminho or not Path(caminho).exists():
            # documento "deixado salvo": gera o PDF na primeira abertura
            caminho = _gerar_pdf_receita(con, doc_id)
            con.commit()
    finally:
        con.close()
    return FileResponse(caminho, media_type="application/pdf",
                        content_disposition_type="inline")
