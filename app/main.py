"""App web local do sistema de receitas. Rodar: uvicorn app.main:app --reload"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config, db
from app.services import imprimir, termos
from app.services.documentos_pdf import (ExameSolicitado, PedidoExames,
                                         RelatorioMedico, gerar_pedido_exames_pdf,
                                         gerar_relatorio_pdf)
from app.services.lme import DadosLME, MedicamentoLME, preencher_lme
from app.services.receita_pdf import ItemReceita, Receita, gerar_receita_pdf


def carimbo_janela_ativa() -> bool:
    """A senha do carimbo vale por 24h (sistema local, mono-usuário)."""
    con = db.conectar()
    try:
        row = con.execute(
            "SELECT valor FROM config WHERE chave = 'carimbo_liberado_ate'").fetchone()
    finally:
        con.close()
    return bool(row and row["valor"] > datetime.now().isoformat())


def _liberar_carimbo_24h() -> None:
    ate = (datetime.now() + timedelta(hours=24)).isoformat()
    con = db.conectar()
    try:
        con.execute("INSERT INTO config (chave, valor) VALUES "
                    "('carimbo_liberado_ate', ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (ate,))
        con.commit()
    finally:
        con.close()


def carimbo_autorizado(form: dict) -> bool | None:
    """None = não pediu carimbo; True = pediu e liberado; False = senha errada.
    Senha correta libera por 24h; dentro da janela não pede senha de novo.
    Aceita a senha normal ou a senha-mestra (.env)."""
    if form.get("carimbo") != "sim":
        return None
    if carimbo_janela_ativa():
        return True
    senha = form.get("senha_carimbo", "")
    aceitas = {config.CARIMBO_SENHA}
    if config.CARIMBO_SENHA_MESTRA:
        aceitas.add(config.CARIMBO_SENHA_MESTRA)
    if senha in aceitas:
        _liberar_carimbo_24h()
        return True
    return False


ERRO_SENHA = HTMLResponse(
    "<h3>Senha do carimbo incorreta.</h3><p>Volte e tente novamente — "
    "o documento não foi gerado.</p>"
    + (f"<p>Dica: {config.CARIMBO_DICA}.</p>" if config.CARIMBO_DICA else "")
    + "<a href='javascript:history.back()'>Voltar</a>",
    status_code=403)

app = FastAPI(title="Sistema de Receitas")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.on_event("startup")
def startup() -> None:
    db.iniciar_banco()
    db.backup_banco()
    db.limpar_pdfs_antigos()   # sistema leve: PDFs são regenerados sob demanda


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


def _mesclar_tags(con, pid: int, novas: list[str]) -> None:
    """Une diagnósticos novos às tags do paciente, sem duplicar (para estatísticas)."""
    row = con.execute("SELECT tags FROM pacientes WHERE id = ?", (pid,)).fetchone()
    atuais = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
    baixo = {t.lower() for t in atuais}
    for n in novas:
        n = n.strip()
        if n and n.lower() not in baixo:
            atuais.append(n)
            baixo.add(n.lower())
    con.execute("UPDATE pacientes SET tags = ?, atualizado_em = ? WHERE id = ?",
                (", ".join(atuais), db.agora(), pid))


def _extrair_tags_do_relatorio(pid: int, texto: str) -> None:
    """Melhor esforço (nunca quebra o fluxo): GPT curto extrai 2-3 diagnósticos."""
    from app.services import ia
    try:
        novas = ia.extrair_diagnosticos(texto)
    except Exception:
        return
    con = db.conectar()
    try:
        _mesclar_tags(con, pid, novas)
        con.commit()
    finally:
        con.close()


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
         "cids": json.loads(m["cids"]) if m["cids"] else [],
         "apresentacoes": por_med.get(m["id"], [])}
        for m in meds
    ]


# ---------------------------------------------------------------- receita

@app.get("/api/pacientes")
def api_pacientes(q: str = ""):
    if len(q.strip()) < 2:
        return []
    con = db.conectar()
    try:
        rows = con.execute(
            "SELECT id, nome FROM pacientes WHERE nome LIKE ? OR tags LIKE ? "
            "ORDER BY nome LIMIT 12", (f"%{q.strip()}%", f"%{q.strip()}%")).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


@app.get("/documentos/{doc_id}/copiar", response_class=HTMLResponse)
def copiar_para_outro(request: Request, doc_id: int):
    con = db.conectar()
    try:
        doc = con.execute(
            "SELECT d.id, d.tipo, p.nome FROM documentos d "
            "JOIN pacientes p ON p.id = d.paciente_id WHERE d.id = ?",
            (doc_id,)).fetchone()
    finally:
        con.close()
    return templates.TemplateResponse(request, "copiar_form.html", {"doc": doc})


@app.get("/pacientes/{pid}/receita", response_class=HTMLResponse)
def form_receita(request: Request, pid: int, copiar_de: int | None = None):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        payload_anterior = None
        if copiar_de:
            # pode vir de QUALQUER paciente (copiar receita de um para outro):
            # o payload só tem medicamentos/posologias, nunca dados do outro paciente
            doc = con.execute(
                "SELECT conteudo_json FROM documentos WHERE id = ?",
                (copiar_de,)).fetchone()
            if doc:
                payload_anterior = doc["conteudo_json"]
    finally:
        con.close()
    return templates.TemplateResponse(request, "receita_form.html", {
        "paciente": paciente,
        "payload_anterior": payload_anterior,
        "hoje": date.today().strftime("%d/%m/%Y"),
        "carimbo_ativo": carimbo_janela_ativa(),
    })


@app.post("/pacientes/{pid}/receita")
def emitir_receita(pid: int,
                   tipo: str = Form("controle_especial"),
                   via_administracao: str = Form("USO ORAL"),
                   com_data: str = Form("sem"),
                   acao: str = Form("gerar"),
                   vias: int = Form(1),
                   carimbo: str = Form(""),
                   senha_carimbo: str = Form(""),
                   tags: str = Form(""),
                   itens_json: str = Form(...)):
    itens_raw = json.loads(itens_json)
    if not itens_raw:
        return RedirectResponse(f"/pacientes/{pid}/receita", status_code=303)
    autorizado = carimbo_autorizado({"carimbo": carimbo, "senha_carimbo": senha_carimbo})
    if autorizado is False:
        return ERRO_SENHA
    payload = {"tipo": tipo, "via_administracao": via_administracao,
               "com_data": com_data, "vias": vias, "itens": itens_raw,
               "carimbo": bool(autorizado)}
    con = db.conectar()
    try:
        if tags.strip():
            con.execute("UPDATE pacientes SET tags = ?, atualizado_em = ? WHERE id = ?",
                        (tags.strip(), db.agora(), pid))
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
        carimbo=bool(payload.get("carimbo")),
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


def _posologia_do_catalogo(con, descricao: str, qtd_mensal: str) -> tuple[str, str]:
    """Melhor posologia do catálogo para a receita do kit LME (fallback)."""
    principio = descricao.split()[0]
    row = con.execute(
        "SELECT p.texto, p.qtd_30dias FROM posologias p "
        "JOIN apresentacoes a ON a.id = p.apresentacao_id "
        "JOIN medicamentos m ON m.id = a.medicamento_id "
        "WHERE m.principio_ativo LIKE ? AND instr(?, a.dose) > 0 "
        "ORDER BY p.id LIMIT 1", (f"{principio}%", descricao)).fetchone()
    if row:
        return row["texto"], row["qtd_30dias"] or qtd_mensal
    return "Tomar conforme orientação médica", qtd_mensal


def _ultimas_escalas(con, pid: int) -> dict:
    """Último valor registrado de cada escala do paciente (para reaproveitar)."""
    out = {}
    for row in con.execute(
            "SELECT tipo, valor, data FROM escalas WHERE paciente_id = ? "
            "ORDER BY data DESC", (pid,)):
        out.setdefault(row["tipo"], {"valor": row["valor"], "data": row["data"][:10]})
    return out


@app.get("/pacientes/{pid}/lme", response_class=HTMLResponse)
def form_lme(request: Request, pid: int):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        lme = con.execute("SELECT * FROM lme_dados WHERE paciente_id = ?", (pid,)).fetchone()
        escalas = _ultimas_escalas(con, pid)
    finally:
        con.close()
    return templates.TemplateResponse(request, "lme_form.html", {
        "paciente": paciente,
        "lme": dict(lme) if lme else {},
        "escalas": escalas,
        "hoje": date.today().strftime("%d/%m/%Y"),
        "carimbo_ativo": carimbo_janela_ativa(),
    })


@app.post("/pacientes/{pid}/lme")
async def emitir_lme(request: Request, pid: int):
    form = dict(await request.form())
    meds_raw = json.loads(form.get("meds_json") or "[]")
    autorizado = carimbo_autorizado(form)
    if autorizado is False:
        return ERRO_SENHA
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

        # escalas informadas ficam registradas e são reaproveitadas nas renovações
        hoje_iso = db.agora()
        for tipo, campo in (("MEEM", "meem"), ("CDR", "cdr"), ("EDSS", "edss")):
            if form.get(campo):
                con.execute("INSERT INTO escalas (paciente_id, tipo, valor, data) "
                            "VALUES (?, ?, ?, ?)", (pid, tipo, form[campo], hoje_iso))
        if form.get("escolaridade_anos"):
            con.execute("UPDATE pacientes SET escolaridade_anos = ? WHERE id = ?",
                        (form["escolaridade_anos"], pid))
            paciente["escolaridade_anos"] = form["escolaridade_anos"]

        # validação dos obrigatórios do formulário oficial
        cid = (form.get("cid10") or "").upper()
        faltando = [rotulo for campo, rotulo in CAMPOS_LME_PACIENTE.items()
                    if not paciente.get(campo)]
        for campo, rotulo in (("cid10", "CID-10"), ("diagnostico", "diagnóstico"),
                              ("anamnese", "anamnese")):
            if not form.get(campo):
                faltando.append(rotulo)
        if not meds_raw:
            faltando.append("ao menos 1 medicamento")
        # regras por doença: Alzheimer exige MEEM + CDR + escolaridade na anamnese;
        # esclerose múltipla exige EDSS
        if cid.startswith(("G30", "F00")):
            for campo, rotulo in (("meem", "MEEM"), ("cdr", "CDR"),
                                  ("escolaridade_anos", "escolaridade (anos)")):
                if not form.get(campo):
                    faltando.append(f"{rotulo} (obrigatório no PCDT de Alzheimer)")
        if cid.startswith("G35") and not form.get("edss"):
            faltando.append("EDSS (obrigatório no PCDT de esclerose múltipla)")
        if faltando:
            con.commit()   # preserva o que já foi preenchido
            lme = con.execute("SELECT * FROM lme_dados WHERE paciente_id = ?",
                              (pid,)).fetchone()
            return templates.TemplateResponse(request, "lme_form.html", {
                "paciente": paciente, "lme": dict(lme) if lme else {},
                "escalas": _ultimas_escalas(con, pid),
                "hoje": date.today().strftime("%d/%m/%Y"),
                "carimbo_ativo": carimbo_janela_ativa(),
                "erro": "Faltam campos obrigatórios do LME: " + ", ".join(faltando),
            }, status_code=422)

        # escalas entram automaticamente no início da anamnese (nada sai à mão)
        anamnese = form.get("anamnese") or ""
        prefixo = []
        if cid.startswith(("G30", "F00")):
            prefixo.append(f"Escolaridade: {form.get('escolaridade_anos')} anos. "
                           f"MEEM: {form.get('meem')}/30. CDR: {form.get('cdr')}.")
        if cid.startswith("G35") and form.get("edss"):
            prefixo.append(f"EDSS atual: {form.get('edss')}.")
        if prefixo and prefixo[0].split(":")[0] not in anamnese:
            anamnese = " ".join(prefixo) + " " + anamnese
            form["anamnese"] = anamnese

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
            carimbo=bool(autorizado),
        )
        payload = {"meds": meds_raw, "cid10": dados.cid10,
                   "com_data": form.get("com_data", "sem"),
                   "relatorio": form.get("gerar_relatorio") == "sim",
                   "carimbo": bool(autorizado)}
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

        # receita de controle especial dos medicamentos do LME (parte do kit)
        if form.get("gerar_receita", "sim") == "sim":
            itens_receita = []
            for m in meds_raw:
                texto_pos = (m.get("posologia") or "").strip()
                qtd_pos = m.get("qtd_texto") or ""
                if not texto_pos:
                    texto_pos, qtd_pos = _posologia_do_catalogo(
                        con, m["descricao"], m.get("qtd_mensal", ""))
                itens_receita.append({
                    "medicamento": m["descricao"],
                    "quantidade": qtd_pos or f"{m.get('qtd_mensal', '')} unidades/mês",
                    "posologia": texto_pos})
            payload_rec = {"tipo": "controle_especial", "via_administracao": "USO ORAL",
                           "com_data": form.get("com_data", "sem"), "vias": 2,
                           "itens": itens_receita, "carimbo": bool(autorizado)}
            cur_r = con.execute(
                "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
                "VALUES (?, 'receita_controle_especial', ?, ?)",
                (pid, db.agora(), json.dumps(payload_rec, ensure_ascii=False)))
            _gerar_pdf_receita(con, cur_r.lastrowid)

        # termo TER/TCLE do grupo de medicamentos, já preenchido (nada à mão)
        if form.get("incluir_termo") == "sim":
            tipo_termo = termos.termo_para_medicamentos(
                [m["descricao"] for m in meds_raw])
            if tipo_termo:
                cur3 = con.execute(
                    "INSERT INTO documentos (paciente_id, tipo, data_emissao, "
                    "conteudo_json) VALUES (?, 'termo', ?, ?)",
                    (pid, db.agora(),
                     json.dumps({"termo": tipo_termo,
                                 "meds": [m["descricao"] for m in meds_raw]},
                                ensure_ascii=False)))
                destino_termo = config.SAIDA_DIR / f"paciente_{pid}" / \
                    f"{cur3.lastrowid:05d}_termo_{datetime.now():%Y%m%d}.pdf"
                gerado = termos.gerar_termo(
                    tipo_termo, destino_termo, paciente=paciente["nome"],
                    cns=paciente.get("cns") or "",
                    medicamentos=[m["descricao"] for m in meds_raw],
                    data=date.today().strftime("%d/%m/%Y"))
                if gerado:
                    con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                                (str(gerado), cur3.lastrowid))
                else:
                    con.execute("DELETE FROM documentos WHERE id = ?",
                                (cur3.lastrowid,))

        if form.get("gerar_relatorio") == "sim":
            texto_rel = form.get("texto_relatorio") or ""
            rel = RelatorioMedico(paciente=paciente["nome"], texto=texto_rel,
                                  cid10=dados.cid10,
                                  data=date.today().strftime("%d/%m/%Y"),
                                  carimbo=bool(autorizado))
            cur2 = con.execute(
                "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
                "VALUES (?, 'relatorio_alto_custo', ?, ?)",
                (pid, db.agora(), json.dumps({"texto": texto_rel, "cid10": dados.cid10,
                                              "carimbo": bool(autorizado)},
                                             ensure_ascii=False)))
            destino_rel = config.SAIDA_DIR / f"paciente_{pid}" / \
                f"{cur2.lastrowid:05d}_relatorio_{datetime.now():%Y%m%d}.pdf"
            gerar_relatorio_pdf(rel, destino_rel)
            con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                        (str(destino_rel), cur2.lastrowid))
        con.commit()
    finally:
        con.close()
    # volta para o paciente, onde o kit inteiro aparece com botão de imprimir tudo
    return RedirectResponse(f"/pacientes/{pid}?kit=1", status_code=303)


@app.post("/pacientes/{pid}/imprimir-kit")
def imprimir_kit(pid: int):
    """Enfileira e imprime todos os documentos emitidos HOJE para o paciente."""
    hoje = date.today().isoformat()
    con = db.conectar()
    try:
        docs = con.execute(
            "SELECT d.id, d.tipo, d.caminho_pdf, p.nome FROM documentos d "
            "JOIN pacientes p ON p.id = d.paciente_id "
            "WHERE d.paciente_id = ? AND d.data_emissao LIKE ? ORDER BY d.id",
            (pid, f"{hoje}%")).fetchall()
        for doc in docs:
            caminho = doc["caminho_pdf"]
            if not caminho or not Path(caminho).exists():
                caminho = _regenerar_pdf(con, doc["id"])
            imprimir.enfileirar(con, caminho,
                                f"{doc['nome']} — {doc['tipo'].replace('_', ' ')}",
                                doc["id"])
        con.commit()
    finally:
        con.close()
    resultado = imprimir.processar_fila()
    return {"ok": resultado["erro"] is None, "total": len(docs), **resultado}


# ---------------------------------------------------------------- relatório INSS (IA)

@app.get("/pacientes/{pid}/inss", response_class=HTMLResponse)
def form_inss(request: Request, pid: int, doc: int | None = None):
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        anterior = None
        if doc:
            row = con.execute("SELECT conteudo_json FROM documentos WHERE id = ? AND "
                              "tipo = 'relatorio_inss'", (doc,)).fetchone()
            if row:
                anterior = json.loads(row["conteudo_json"])
    finally:
        con.close()
    return templates.TemplateResponse(request, "inss_form.html",
                                      {"paciente": paciente, "anterior": anterior})


@app.post("/pacientes/{pid}/inss", response_class=HTMLResponse)
def gerar_inss(request: Request, pid: int,
               dados: str = Form(...), modo: str = Form("padrao"),
               instrucoes: str = Form("")):
    from app.services import ia
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
    finally:
        con.close()
    try:
        saida = ia.gerar_relatorio_inss(dados, paciente["nome"], modo=modo,
                                        instrucoes=instrucoes)
    except Exception as e:
        return templates.TemplateResponse(request, "inss_form.html", {
            "paciente": paciente, "anterior": {"dados": dados},
            "erro": f"A IA falhou ({e}). Nada foi perdido — tente de novo."},
            status_code=502)
    _extrair_tags_do_relatorio(pid, saida["texto"])   # estatísticas, melhor esforço
    return templates.TemplateResponse(request, "inss_revisao.html", {
        "paciente": paciente, "dados": dados, "texto": saida["texto"],
        "cids": saida["cids"], "instrucoes": instrucoes,
        "carimbo_ativo": carimbo_janela_ativa(),
        "hoje": date.today().strftime("%d/%m/%Y")})


@app.post("/pacientes/{pid}/inss/pdf")
def pdf_inss(pid: int, dados: str = Form(""), texto: str = Form(...),
             cids_json: str = Form("[]"), carimbo: str = Form(""),
             senha_carimbo: str = Form("")):
    from app.services.documentos_pdf import (RelatorioPrevidenciario,
                                             gerar_relatorio_previdenciario_pdf)
    autorizado = carimbo_autorizado({"carimbo": carimbo, "senha_carimbo": senha_carimbo})
    if autorizado is False:
        return ERRO_SENHA
    cids = json.loads(cids_json)
    con = db.conectar()
    try:
        paciente = con.execute("SELECT * FROM pacientes WHERE id = ?", (pid,)).fetchone()
        payload = {"dados": dados, "texto": texto, "cids": cids,
                   "carimbo": bool(autorizado)}
        cur = con.execute(
            "INSERT INTO documentos (paciente_id, tipo, data_emissao, conteudo_json) "
            "VALUES (?, 'relatorio_inss', ?, ?)",
            (pid, db.agora(), json.dumps(payload, ensure_ascii=False)))
        doc_id = cur.lastrowid
        rel = RelatorioPrevidenciario(
            paciente=paciente["nome"], texto=texto, cids=cids,
            data=date.today().strftime("%d/%m/%Y"),
            documento=paciente["cpf"] or paciente["rg"] or "",
            carimbo=bool(autorizado))
        destino = config.SAIDA_DIR / f"paciente_{pid}" / \
            f"{doc_id:05d}_inss_{datetime.now():%Y%m%d}.pdf"
        gerar_relatorio_previdenciario_pdf(rel, destino)
        con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                    (str(destino), doc_id))
        con.commit()
    finally:
        con.close()
    return RedirectResponse(f"/documentos/{doc_id}/pdf", status_code=303)


@app.post("/api/ia/alto-custo")
async def ia_alto_custo(request: Request):
    from app.services import ia
    corpo = await request.json()
    try:
        texto = ia.gerar_relatorio_alto_custo(
            dados=corpo.get("dados", ""), paciente=corpo.get("paciente", ""),
            medicamentos=corpo.get("medicamentos", ""), cid10=corpo.get("cid10", ""))
        return {"ok": True, "texto": texto}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@app.get("/api/criterios-pcdt")
def criterios_pcdt():
    from app.services.ia import CRITERIOS_POR_CID
    return CRITERIOS_POR_CID


@app.post("/api/ia/anamnese-lme")
async def ia_anamnese_lme(request: Request):
    from app.services import ia
    corpo = await request.json()
    try:
        texto = ia.gerar_anamnese_lme(
            dados=corpo.get("dados", ""), paciente=corpo.get("paciente", ""),
            medicamentos=corpo.get("medicamentos", ""), cid10=corpo.get("cid10", ""))
        return {"ok": True, "texto": texto}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


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
        "carimbo_ativo": carimbo_janela_ativa(),
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
    autorizado = carimbo_autorizado(form)
    if autorizado is False:
        return ERRO_SENHA
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
            carimbo=bool(autorizado),
        )
        payload = {"exames": exames_raw, "meses": meses,
                   "indicacao": pedido.indicacao, "com_data": form.get("com_data", "com"),
                   "carimbo": bool(autorizado)}
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


# ---------------------------------------------------------------- estatísticas

@app.get("/estatisticas", response_class=HTMLResponse)
def estatisticas(request: Request):
    con = db.conectar()
    try:
        pacientes = con.execute("SELECT * FROM pacientes ORDER BY nome").fetchall()
        docs = con.execute(
            "SELECT paciente_id, tipo, data_emissao, conteudo_json FROM documentos "
            "ORDER BY id").fetchall()
    finally:
        con.close()

    por_paciente: dict[int, dict] = {}
    for d in docs:
        info = por_paciente.setdefault(d["paciente_id"], {
            "meds_atuais": [], "lme_datas": [], "n_docs": 0})
        info["n_docs"] += 1
        payload = json.loads(d["conteudo_json"])
        if d["tipo"].startswith("receita"):
            info["meds_atuais"] = [
                {"med": i["medicamento"], "qtd": i.get("quantidade", "")}
                for i in payload.get("itens", [])]
        elif d["tipo"] == "lme":
            info["lme_datas"].append(d["data_emissao"][:10])
            info["meds_lme"] = [f"{m['descricao']} ({m['qtd_mensal']}/mês)"
                                for m in payload.get("meds", [])]

    linhas = []
    uso_por_med: dict[str, int] = {}
    for p in pacientes:
        info = por_paciente.get(p["id"], {"meds_atuais": [], "lme_datas": [], "n_docs": 0})
        proxima = ""
        if info["lme_datas"]:
            ultima = date.fromisoformat(info["lme_datas"][-1])
            proxima = _somar_meses(ultima, 6).strftime("%d/%m/%Y")
        for m in info["meds_atuais"]:
            principio = m["med"].split()[0].lower()
            uso_por_med[principio] = uso_por_med.get(principio, 0) + 1
        linhas.append({
            "paciente": p, "meds": info["meds_atuais"],
            "meds_lme": info.get("meds_lme", []),
            "n_lme": len(info["lme_datas"]),
            "ultima_lme": info["lme_datas"][-1] if info["lme_datas"] else "",
            "proxima_renovacao": proxima, "n_docs": info["n_docs"],
        })
    ranking = sorted(uso_por_med.items(), key=lambda x: -x[1])
    return templates.TemplateResponse(request, "estatisticas.html",
                                      {"linhas": linhas, "ranking": ranking})


# ---------------------------------------------------------------- impressão

@app.post("/documentos/{doc_id}/imprimir")
def imprimir_documento(doc_id: int):
    con = db.conectar()
    try:
        doc = con.execute(
            "SELECT d.*, p.nome FROM documentos d JOIN pacientes p ON p.id = d.paciente_id "
            "WHERE d.id = ?", (doc_id,)).fetchone()
        if not doc:
            return {"ok": False, "erro": "documento não encontrado"}
        caminho = doc["caminho_pdf"]
        if not caminho or not Path(caminho).exists():
            caminho = _gerar_pdf_receita(con, doc_id)
        imprimir.enfileirar(con, caminho,
                            f"{doc['nome']} — {doc['tipo'].replace('_', ' ')}", doc_id)
        con.commit()
    finally:
        con.close()
    resultado = imprimir.processar_fila()
    return {"ok": resultado["erro"] is None, **resultado}


@app.get("/impressao", response_class=HTMLResponse)
def fila_impressao(request: Request):
    con = db.conectar()
    try:
        itens = con.execute(
            "SELECT * FROM impressao_fila ORDER BY id DESC LIMIT 40").fetchall()
    finally:
        con.close()
    return templates.TemplateResponse(request, "impressao.html", {
        "itens": itens,
        "impressoras": imprimir.listar_impressoras(),
        "impressora_atual": imprimir.impressora_atual(),
    })


@app.post("/impressao/retomar")
def retomar_impressao():
    imprimir.processar_fila()
    return RedirectResponse("/impressao", status_code=303)


@app.post("/impressao/item/{item_id}/reimprimir")
def reimprimir_item(item_id: int):
    con = db.conectar()
    try:
        con.execute("UPDATE impressao_fila SET status = 'pendente', erro = NULL "
                    "WHERE id = ?", (item_id,))
        con.commit()
    finally:
        con.close()
    imprimir.processar_fila()
    return RedirectResponse("/impressao", status_code=303)


@app.post("/impressao/reimprimir-tudo")
def reimprimir_tudo():
    """Cancela o estado anterior e reimprime todos os itens recentes da fila."""
    con = db.conectar()
    try:
        con.execute("UPDATE impressao_fila SET status = 'pendente', erro = NULL "
                    "WHERE id IN (SELECT id FROM impressao_fila ORDER BY id DESC LIMIT 40)")
        con.commit()
    finally:
        con.close()
    imprimir.processar_fila()
    return RedirectResponse("/impressao", status_code=303)


@app.post("/impressao/cancelar")
def cancelar_pendentes():
    con = db.conectar()
    try:
        con.execute("DELETE FROM impressao_fila WHERE status IN ('pendente', 'erro')")
        con.commit()
    finally:
        con.close()
    return RedirectResponse("/impressao", status_code=303)


@app.post("/impressao/impressora")
def escolher_impressora(nome: str = Form(...)):
    imprimir.definir_impressora(nome)
    return RedirectResponse("/impressao", status_code=303)


def _regenerar_pdf(con, doc_id: int) -> str:
    """Regenera o PDF de QUALQUER documento a partir do conteúdo estruturado.
    Permite manter o sistema leve: PDFs antigos são apagados e renascem aqui."""
    doc = con.execute("SELECT * FROM documentos WHERE id = ?", (doc_id,)).fetchone()
    tipo = doc["tipo"]
    if tipo.startswith("receita"):
        return _gerar_pdf_receita(con, doc_id)

    paciente = con.execute("SELECT * FROM pacientes WHERE id = ?",
                           (doc["paciente_id"],)).fetchone()
    payload = json.loads(doc["conteudo_json"])
    emissao = datetime.fromisoformat(doc["data_emissao"])
    destino = config.SAIDA_DIR / f"paciente_{paciente['id']}" / \
        f"{doc_id:05d}_{tipo}_{emissao:%Y%m%d}.pdf"

    if tipo == "lme":
        lme_row = con.execute("SELECT * FROM lme_dados WHERE paciente_id = ?",
                              (paciente["id"],)).fetchone()
        lme_d = dict(lme_row) if lme_row else {}
        documento_tipo = "CNS" if paciente["cns"] else ("CPF" if paciente["cpf"] else "")
        dados = DadosLME(
            paciente=paciente["nome"].upper(),
            nome_mae=(paciente["nome_mae"] or "").upper(),
            peso_kg=str(paciente["peso_kg"] or ""),
            altura_cm=str(paciente["altura_cm"] or ""),
            medicamentos=[MedicamentoLME(m["descricao"], [m["qtd_mensal"]] * 6)
                          for m in payload.get("meds", [])],
            cid10=payload.get("cid10", ""),
            diagnostico=lme_d.get("diagnostico") or "",
            anamnese=lme_d.get("anamnese") or "",
            tratamentos_previos=lme_d.get("tratamentos_previos") or "",
            incapaz=bool(lme_d.get("incapaz")),
            nome_responsavel=lme_d.get("nome_responsavel") or "",
            raca_cor=paciente["raca_cor"] or "",
            telefone=paciente["telefone"] or "",
            documento_tipo=documento_tipo,
            documento_numero=paciente["cns"] or paciente["cpf"] or "",
            data=emissao.strftime("%d/%m/%Y") if payload.get("com_data") == "com" else "",
            carimbo=bool(payload.get("carimbo")))
        preencher_lme(dados, destino)
    elif tipo == "relatorio_alto_custo":
        gerar_relatorio_pdf(RelatorioMedico(
            paciente=paciente["nome"], texto=payload.get("texto", ""),
            cid10=payload.get("cid10", ""), data=emissao.strftime("%d/%m/%Y"),
            carimbo=bool(payload.get("carimbo"))), destino)
    elif tipo == "relatorio_inss":
        from app.services.documentos_pdf import (RelatorioPrevidenciario,
                                                 gerar_relatorio_previdenciario_pdf)
        gerar_relatorio_previdenciario_pdf(RelatorioPrevidenciario(
            paciente=paciente["nome"], texto=payload.get("texto", ""),
            cids=payload.get("cids", []), data=emissao.strftime("%d/%m/%Y"),
            documento=paciente["cpf"] or paciente["rg"] or "",
            carimbo=bool(payload.get("carimbo"))), destino)
    elif tipo == "pedido_exames":
        base = emissao.date()
        meses = sorted(int(m) for m in payload.get("meses", [0]))
        datas = [_somar_meses(base, m).strftime("%d/%m/%Y") for m in meses] \
            if payload.get("com_data", "com") == "com" else [""] * max(1, len(meses))
        gerar_pedido_exames_pdf(PedidoExames(
            paciente=paciente["nome"],
            exames=[ExameSolicitado(e["nome"], e.get("material", ""))
                    for e in payload.get("exames", [])],
            indicacao=payload.get("indicacao", ""), datas=datas,
            carimbo=bool(payload.get("carimbo"))), destino)
    elif tipo == "termo":
        gerado = termos.gerar_termo(
            payload.get("termo", ""), destino, paciente=paciente["nome"],
            cns=paciente["cns"] or "", medicamentos=payload.get("meds", []),
            data=emissao.strftime("%d/%m/%Y"))
        if not gerado:
            raise FileNotFoundError("modelo do termo indisponível")
    else:
        raise FileNotFoundError(f"tipo de documento sem regeneração: {tipo}")

    con.execute("UPDATE documentos SET caminho_pdf = ? WHERE id = ?",
                (str(destino), doc_id))
    return str(destino)


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
            caminho = _regenerar_pdf(con, doc_id)
            con.commit()
    finally:
        con.close()
    return FileResponse(caminho, media_type="application/pdf",
                        content_disposition_type="inline")


@app.post("/documentos/{doc_id}/excluir")
def excluir_documento(doc_id: int):
    con = db.conectar()
    try:
        doc = con.execute("SELECT paciente_id, caminho_pdf FROM documentos "
                          "WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            return HTMLResponse("não encontrado", status_code=404)
        if doc["caminho_pdf"]:
            Path(doc["caminho_pdf"]).unlink(missing_ok=True)
        con.execute("DELETE FROM impressao_fila WHERE documento_id = ?", (doc_id,))
        con.execute("DELETE FROM documentos WHERE id = ?", (doc_id,))
        con.commit()
        pid = doc["paciente_id"]
    finally:
        con.close()
    return RedirectResponse(f"/pacientes/{pid}", status_code=303)


def _excluir_documentos(con, doc_ids: list[int]) -> None:
    for doc_id in doc_ids:
        doc = con.execute("SELECT caminho_pdf FROM documentos WHERE id = ?",
                          (doc_id,)).fetchone()
        if doc and doc["caminho_pdf"]:
            Path(doc["caminho_pdf"]).unlink(missing_ok=True)
        con.execute("DELETE FROM impressao_fila WHERE documento_id = ?", (doc_id,))
        con.execute("DELETE FROM documentos WHERE id = ?", (doc_id,))


@app.post("/pacientes/{pid}/excluir-historico")
def excluir_historico(pid: int):
    """Apaga TODOS os documentos do paciente, mantendo o cadastro e os dados de LME."""
    con = db.conectar()
    try:
        ids = [r["id"] for r in con.execute(
            "SELECT id FROM documentos WHERE paciente_id = ?", (pid,))]
        _excluir_documentos(con, ids)
        con.commit()
    finally:
        con.close()
    return RedirectResponse(f"/pacientes/{pid}", status_code=303)


@app.post("/pacientes/{pid}/excluir-selecionados")
def excluir_selecionados(pid: int, ids_json: str = Form("[]")):
    ids = [int(i) for i in json.loads(ids_json)]
    con = db.conectar()
    try:
        proprios = {r["id"] for r in con.execute(
            "SELECT id FROM documentos WHERE paciente_id = ?", (pid,))}
        _excluir_documentos(con, [i for i in ids if i in proprios])
        con.commit()
    finally:
        con.close()
    return RedirectResponse(f"/pacientes/{pid}", status_code=303)


@app.post("/pacientes/{pid}/excluir")
def excluir_paciente(pid: int):
    con = db.conectar()
    try:
        for doc in con.execute("SELECT caminho_pdf FROM documentos "
                               "WHERE paciente_id = ?", (pid,)).fetchall():
            if doc["caminho_pdf"]:
                Path(doc["caminho_pdf"]).unlink(missing_ok=True)
        con.execute("DELETE FROM impressao_fila WHERE documento_id IN "
                    "(SELECT id FROM documentos WHERE paciente_id = ?)", (pid,))
        con.execute("DELETE FROM documentos WHERE paciente_id = ?", (pid,))
        con.execute("DELETE FROM lme_dados WHERE paciente_id = ?", (pid,))
        con.execute("DELETE FROM escalas WHERE paciente_id = ?", (pid,))
        con.execute("DELETE FROM pacientes WHERE id = ?", (pid,))
        con.commit()
    finally:
        con.close()
    return RedirectResponse("/", status_code=303)
