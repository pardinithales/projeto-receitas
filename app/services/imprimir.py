"""Impressão direta via SumatraPDF (silenciosa) com fila e retomada.

Fluxo: documentos entram na fila (tabela impressao_fila) e são impressos em
sequência. Se der erro (papel acabou, impressora offline), os itens restantes
ficam 'pendente' e o botão Retomar imprime só o que faltou.
"""
import subprocess

from app import config, db


def listar_impressoras() -> list[str]:
    try:
        saida = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=20)
        nomes = [l.strip() for l in saida.stdout.splitlines() if l.strip()]
        # impressoras virtuais não interessam para o consultório
        return [n for n in nomes if not any(
            v in n for v in ("OneNote", "Microsoft Print", "Fax", "XPS"))] or nomes
    except Exception:
        return []


def impressora_atual(con=None) -> str:
    fechar = con is None
    con = con or db.conectar()
    try:
        row = con.execute("SELECT valor FROM config WHERE chave = 'impressora'").fetchone()
        return row["valor"] if row else config.IMPRESSORA_PADRAO
    finally:
        if fechar:
            con.close()


def definir_impressora(nome: str) -> None:
    con = db.conectar()
    try:
        con.execute("INSERT INTO config (chave, valor) VALUES ('impressora', ?) "
                    "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (nome,))
        con.commit()
    finally:
        con.close()


def imprimir_pdf(caminho: str, impressora: str) -> tuple[bool, str]:
    if not config.SUMATRA_PATH.exists():
        return False, ("SumatraPDF não encontrado em tools/sumatra — baixe o portátil "
                       "ou configure SUMATRA_PATH no .env")
    try:
        r = subprocess.run(
            [str(config.SUMATRA_PATH), "-print-to", impressora, "-silent",
             "-exit-when-done", caminho],
            capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return True, "ok"
        return False, f"impressão falhou (código {r.returncode}) {r.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return False, "tempo esgotado — impressora sem papel ou offline?"
    except OSError as e:
        return False, str(e)


def enfileirar(con, caminho: str, descricao: str, documento_id: int | None = None) -> int:
    cur = con.execute(
        "INSERT INTO impressao_fila (documento_id, caminho, descricao, criado_em) "
        "VALUES (?, ?, ?, ?)", (documento_id, caminho, descricao, db.agora()))
    return cur.lastrowid


def processar_fila() -> dict:
    """Imprime tudo que está pendente/erro, em ordem. Para no primeiro erro
    (para não desperdiçar papel fora de ordem) e informa onde parou."""
    impressora = impressora_atual()
    con = db.conectar()
    resultado = {"impressos": 0, "erro": None, "restantes": 0}
    try:
        itens = con.execute(
            "SELECT * FROM impressao_fila WHERE status IN ('pendente', 'erro') "
            "ORDER BY id").fetchall()
        for i, item in enumerate(itens):
            ok, msg = imprimir_pdf(item["caminho"], impressora)
            if ok:
                con.execute("UPDATE impressao_fila SET status = 'ok', erro = NULL "
                            "WHERE id = ?", (item["id"],))
                con.commit()
                resultado["impressos"] += 1
            else:
                con.execute("UPDATE impressao_fila SET status = 'erro', erro = ? "
                            "WHERE id = ?", (msg, item["id"]))
                con.commit()
                resultado["erro"] = f"{item['descricao']}: {msg}"
                resultado["restantes"] = len(itens) - i
                break
    finally:
        con.close()
    return resultado
