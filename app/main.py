"""App web local do sistema de receitas. Rodar: uvicorn app.main:app --reload"""
import json
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config, db
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
                "SELECT id, nome, data_nascimento FROM pacientes "
                "WHERE nome LIKE ? ORDER BY nome LIMIT 12",
                (f"%{q.strip()}%",),
            ).fetchall()
        finally:
            con.close()
    return templates.TemplateResponse(request, "_lista_pacientes.html",
                                      {"pacientes": linhas, "q": q})


# ---------------------------------------------------------------- pacientes

CAMPOS_PACIENTE = ["nome", "data_nascimento", "cpf", "cns", "rg", "nome_mae",
                   "peso_kg", "altura_cm", "telefone", "endereco", "cidade", "uf",
                   "raca_cor"]


@app.get("/pacientes/novo", response_class=HTMLResponse)
def novo_paciente(request: Request, nome: str = ""):
    return templates.TemplateResponse(request, "paciente_form.html",
                                      {"paciente": {"nome": nome}})


@app.post("/pacientes")
async def criar_paciente(request: Request):
    form = dict(await request.form())
    valores = [form.get(c) or None for c in CAMPOS_PACIENTE]
    con = db.conectar()
    try:
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


@app.get("/pacientes/{pid}", response_class=HTMLResponse)
def ver_paciente(request: Request, pid: int):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        documentos = con.execute(
            "SELECT id, tipo, data_emissao, conteudo_json FROM documentos "
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
                   itens_json: str = Form(...)):
    itens_raw = json.loads(itens_json)
    if not itens_raw:
        return RedirectResponse(f"/pacientes/{pid}/receita", status_code=303)
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        data_txt = date.today().strftime("%d/%m/%Y") if com_data == "com" else ""
        receita = Receita(
            paciente=paciente["nome"],
            itens=[ItemReceita(i["medicamento"], i["quantidade"], i["posologia"])
                   for i in itens_raw],
            tipo=tipo,
            via_administracao=via_administracao,
            data=data_txt,
        )
        payload = {"tipo": tipo, "via_administracao": via_administracao,
                   "com_data": com_data, "itens": itens_raw}
        cur = con.execute(
            "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
            "VALUES (?, ?, ?, ?)",
            (pid, f"receita_{tipo}", db.agora(), json.dumps(payload, ensure_ascii=False)),
        )
        doc_id = cur.lastrowid
        nome_arq = f"{doc_id:05d}_receita_{datetime.now():%Y%m%d}.pdf"
        destino = config.SAIDA_DIR / f"paciente_{pid}" / nome_arq
        gerar_receita_pdf(receita, destino)
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
    finally:
        con.close()
    if not doc or not doc["caminho_pdf"] or not Path(doc["caminho_pdf"]).exists():
        return HTMLResponse("PDF não encontrado", status_code=404)
    return FileResponse(doc["caminho_pdf"], media_type="application/pdf",
                        content_disposition_type="inline")
