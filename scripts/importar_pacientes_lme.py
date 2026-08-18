"""Importa pacientes reais para o banco LOCAL a partir dos LMEs mais recentes.

Varre apenas os PDFs de LME mais novos (não a pasta inteira), extrai os campos
AcroForm (nome, mãe, peso, altura, CID, diagnóstico, anamnese, tratamentos) e
cadastra paciente + lme_dados no SQLite local. Nada sai da máquina.

Uso:  python scripts/importar_pacientes_lme.py [N_PACIENTES]
"""
import sys
from pathlib import Path

import pikepdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402

PASTA_REAL = Path(r"M:\Thales Pardini - Neurologia\Receitas Thales Pardini - Neurologia")

MAPA = {
    "Nome do paciente": "nome",
    "Nome da mãe do paciente": "nome_mae",
    "Peso": "peso_kg",
    "Altura": "altura_cm",
    "CID": "cid10",
    "Diagnóstico": "diagnostico",
    "Anamnese": "anamnese",
    "tratamentos prévios": "tratamentos_previos",
    "Nome do Responsável": "nome_responsavel",
}


def campos_lme(caminho: Path) -> dict[str, str]:
    dados: dict[str, str] = {}
    with pikepdf.open(caminho) as pdf:
        for page in pdf.pages:
            for annot in page.get("/Annots", []):
                try:
                    t = str(annot.get("/T", ""))
                    v = annot.get("/V")
                    if t in MAPA and v is not None:
                        valor = str(v).strip()
                        if valor and valor != "/Off":
                            dados[MAPA[t]] = valor
                except Exception:
                    continue
    return dados


def eh_lme(caminho: Path) -> bool:
    nome = caminho.name.lower()
    return "lme" in nome and caminho.suffix.lower() == ".pdf"


def main() -> None:
    alvo = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    db.iniciar_banco()
    con = db.conectar()
    candidatos = sorted((p for p in PASTA_REAL.rglob("*.pdf") if eh_lme(p)),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"{len(candidatos)} PDFs de LME encontrados; importando os {alvo} "
          f"pacientes mais recentes…\n")
    importados = 0
    vistos: set[str] = set()
    try:
        for pdf in candidatos:
            if importados >= alvo:
                break
            try:
                dados = campos_lme(pdf)
            except Exception as e:
                print(f"  [erro] {pdf.name[:60]}: {e}")
                continue
            nome = dados.get("nome", "").strip().title()
            if not nome or nome.lower() in vistos:
                continue
            vistos.add(nome.lower())
            ja_existe = con.execute(
                "SELECT id FROM pacientes WHERE nome = ? COLLATE NOCASE", (nome,)
            ).fetchone()
            if ja_existe:
                print(f"  [já existe] {nome}")
                continue
            cur = con.execute(
                "INSERT INTO pacientes (nome, nome_mae, peso_kg, altura_cm, "
                "criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?)",
                (nome, dados.get("nome_mae", "").title() or None,
                 _num(dados.get("peso_kg")), _num(dados.get("altura_cm")),
                 db.agora(), db.agora()),
            )
            pid = cur.lastrowid
            if any(k in dados for k in ("cid10", "diagnostico", "anamnese")):
                con.execute(
                    "INSERT INTO lme_dados (paciente_id, cid10, diagnostico, anamnese, "
                    "tratamentos_previos, nome_responsavel, atualizado_em) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (pid, dados.get("cid10", "").upper() or None,
                     dados.get("diagnostico"), dados.get("anamnese"),
                     dados.get("tratamentos_previos"), dados.get("nome_responsavel"),
                     db.agora()),
                )
            extras = [k for k in ("nome_mae", "peso_kg", "cid10", "anamnese") if k in dados]
            print(f"  [ok] {nome}  (campos: nome, {', '.join(extras)})")
            importados += 1
        con.commit()
    finally:
        con.close()
    print(f"\n{importados} pacientes importados para o banco local.")


def _num(v: str | None) -> float | None:
    if not v:
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


if __name__ == "__main__":
    main()
