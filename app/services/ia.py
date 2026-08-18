"""Geração de texto médico via OpenAI (GPT-5.6 Sol, reasoning medium).

Usado para: relatório para fins previdenciários (INSS) e relatório técnico
para farmácia de alto custo. Os prompts-base são do usuário e ficam FORA do
repositório (caminhos configuráveis no .env); há um resumo embutido como
fallback caso o arquivo não exista.
"""
import json
import os
import re
import time
from pathlib import Path

import httpx

from app import config

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MODELO = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")

PROMPT_INSS_PATH = Path(os.getenv(
    "INSS_PROMPT_PATH",
    r"M:\Thales Pardini - Neurologia\Prompts principais\RELATORIO_INSS_MAIS_ATUAL-13-08-2026.txt"))
PROMPT_ALTO_CUSTO_PATH = Path(os.getenv(
    "ALTO_CUSTO_PROMPT_PATH",
    r"M:\Thales Pardini - Neurologia\Prompts principais\RELATORIO-PARA-LME-FARMACIA-ALTOCUSTO-TODAS-DOENCAS-NEURO-DRAGON.txt"))

FALLBACK_INSS = (
    "Elabore relatório neurológico conciso, técnico e direto para fins previdenciários. "
    "Priorize cronologia com datas, achados alterados de exames, incapacidade funcional "
    "objetiva (fala, deglutição, destreza, marcha, AVDs), frequência de crises e "
    "perspectiva de seguimento. Descreva apenas os déficits presentes. Nunca mencione "
    "o que NÃO está documentado. Sem bullets, sem hifens. CID ao final.")

FALLBACK_ALTO_CUSTO = (
    "Redija sumário médico para LME/Farmácia de Alto Custo. Comece com 'À Farmácia de "
    "Alto Custo'. 3 a 5 parágrafos técnicos: diagnóstico e gravidade; critérios "
    "preenchidos; resultados objetivos de exames; tratamentos prévios/falha quando "
    "houver; indicação explícita do medicamento com dose. Não invente dados. "
    "Finalize com CID-10: código – diagnóstico.")

REGRAS_FIXAS = (
    "\n\nREGRAS ABSOLUTAS DE ESTILO: nunca use travessões (— ou –); nunca use bullets, "
    "listas ou hifens de tópico; escreva em parágrafos corridos; português técnico e "
    "neutro, sem termos rebuscados; nunca dê parecer sobre concessão de benefício; "
    "nunca afirme que algo 'não foi encontrado' ou 'não está disponível'; "
    "evite palavras verbosas ou vagas como 'manejo', 'em investigação', 'complexo', "
    "'abordagem', 'otimização': prefira o termo concreto do que foi feito ou observado. "
    "PROIBIDO frases genéricas e vazias que caberiam em qualquer relatório, como "
    "'necessita seguimento especializado', 'perda funcional relevante', "
    "'comprometimento importante', 'impacto significativo', 'quadro em evolução': "
    "substitua sempre por dados objetivos, mensuráveis e específicos deste caso "
    "(o que o paciente não consegue fazer, com que frequência, desde quando).")


def _prompt_base(qual: str) -> str:
    caminho = PROMPT_INSS_PATH if qual == "inss" else PROMPT_ALTO_CUSTO_PATH
    fallback = FALLBACK_INSS if qual == "inss" else FALLBACK_ALTO_CUSTO
    try:
        return caminho.read_text(encoding="utf-8")
    except OSError:
        return fallback


def limpar_texto(t: str) -> str:
    """Remove travessões (entre dígitos vira hífen; no texto vira vírgula)."""
    t = re.sub(r"(?<=\d)\s*[—–]\s*(?=\d)", "-", t)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    return t.strip()


def _chamar(mensagens: list[dict], schema: dict | None = None,
            tentativas: int = 3) -> str:
    chave = os.getenv("OPENAI_API_KEY", "")
    if not chave:
        raise RuntimeError("OPENAI_API_KEY não configurada no .env")
    corpo: dict = {"model": MODELO, "messages": mensagens,
                   "reasoning_effort": "medium"}
    if schema:
        corpo["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "saida", "strict": True, "schema": schema}}
    ultimo_erro: Exception | None = None
    for i in range(tentativas):
        try:
            r = httpx.post(OPENAI_URL, json=corpo, timeout=300,
                           headers={"Authorization": f"Bearer {chave}"})
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            if r.status_code in (400, 401, 403):    # erro definitivo, não readianta repetir
                raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
            ultimo_erro = RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
        except (httpx.TimeoutException, httpx.TransportError) as e:
            ultimo_erro = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"Falha na API OpenAI após {tentativas} tentativas: {ultimo_erro}")


SCHEMA_INSS = {
    "type": "object",
    "additionalProperties": False,
    "required": ["texto", "cids"],
    "properties": {
        "texto": {"type": "string",
                  "description": "Relatório completo em parágrafos corridos, sem o CID no final (vai em campo próprio)"},
        "cids": {"type": "array", "minItems": 1, "maxItems": 3,
                 "items": {"type": "object", "additionalProperties": False,
                           "required": ["codigo", "descricao"],
                           "properties": {"codigo": {"type": "string"},
                                          "descricao": {"type": "string"}}}},
    },
}


def gerar_relatorio_inss(dados_colados: str, paciente: str,
                         modo: str = "padrao", instrucoes: str = "") -> dict:
    """modo: padrao | conciso | imparcial. Retorna {texto, cids:[{codigo,descricao}]}.
    `instrucoes`: ajustes pontuais do médico nesta geração (não altera o prompt-base,
    que é o arquivo .txt do usuário, editável a qualquer momento)."""
    extra = {"padrao": "",
             "conciso": "\n\nGere uma versão MAIS CONCISA, mantendo apenas o essencial.",
             "imparcial": "\n\nGere uma versão MAIS IMPARCIAL e neutra, apenas fatos "
                          "documentados, sem qualquer juízo de valor."}[modo]
    if instrucoes.strip():
        extra += f"\n\nInstruções adicionais do médico para esta geração: {instrucoes.strip()}"
    sistema = (_prompt_base("inss") + REGRAS_FIXAS + extra +
               "\n\nResponda em JSON: texto do relatório e 2 a 3 sugestões de CID-10 "
               "pertinentes ao caso (código e descrição curta).")
    conteudo = f"Paciente: {paciente}\n\nDados clínicos colados pelo médico:\n{dados_colados}"
    resposta = _chamar([{"role": "system", "content": sistema},
                        {"role": "user", "content": conteudo}], schema=SCHEMA_INSS)
    saida = json.loads(resposta)
    saida["texto"] = limpar_texto(saida["texto"])
    return saida


# Critérios do PCDT que o relatório PRECISA endereçar, por prefixo de CID
# (fonte: docs/pcdt-requisitos-pesquisa.md e fichas SES-SP)
CRITERIOS_POR_CID = {
    "G40": "PCDT Epilepsia (Portaria 17/2018): demonstrar 2 crises não provocadas com "
           ">24h de intervalo OU 1 crise com risco de recorrência >60% OU síndrome "
           "epiléptica definida; descrever semiologia, frequência das crises, EEG e "
           "RM/TC; se farmacorresistência, detalhar fármacos prévios com doses, tempo "
           "de uso, resposta e motivo da troca (falha a 1ª linha do componente básico: "
           "carbamazepina, fenobarbital, fenitoína, valproato).",
    "G70": "PCDT Miastenia Gravis (Portaria 11/2022): fatigabilidade e flutuação, "
           "distribuição (ocular, bulbar, respiratória, apendicular); citar ENMG com "
           "estimulação repetitiva (decremento >=10%), fibra única ou anti-AChR >1 nM; "
           "para imunoglobulina, evidenciar CRISE MIASTÊNICA (SP só libera para crise).",
    "G35": "PCDT Esclerose Múltipla (Portaria 8/2024): demonstrar disseminação no "
           "espaço e no tempo (McDonald 2017), forma clínica, EDSS pontuado, surtos e "
           "atividade radiológica; justificar a linha do medicamento (1ª "
           "interferona/glatirâmer/teriflunomida/fumarato; 2ª fingolimode; 3ª "
           "natalizumabe; alta atividade: natalizumabe 1ª linha); falha = >=1 surto + "
           "4 novas lesões T2 em 1 ano de tratamento adequado.",
    "G61": "PCDT Guillain-Barré (Portaria 1.171/2015): cronologia, fraqueza "
           "ascendente/arreflexia, líquor e ENMG quando documentados, estágio/gravidade "
           "(incapacidade de deambular sem auxílio), dose 0,4 g/kg/dia por 5 dias.",
    "G30": "PCDT Doença de Alzheimer (Portaria 27/2025): informar MEEM e CDR com "
           "valores, data e escolaridade; cortes: IChE leve/moderada MEEM 12-24 (>4 "
           "anos estudo) ou 8-21 (<=4 anos) com CDR 1-2; DA grave (donepezila ou "
           "memantina) MEEM 5-11 ou 3-7 com CDR 3; citar exames de diagnóstico "
           "diferencial e neuroimagem.",
    "F00": "PCDT Doença de Alzheimer: ver critérios de MEEM/CDR por escolaridade e "
           "gravidade; citar neuroimagem e exclusão de causas reversíveis.",
    "R52": "PCDT Dor Crônica (Portaria 1.083/2012): caracterizar dor neuropática com "
           "LANSS (>=12 sugere) e intensidade por EVA; para gabapentina, documentar "
           "falha ou contraindicação a antidepressivo tricíclico.",
    "G20": "PCDT Doença de Parkinson (Portaria 10/2017): diagnóstico pelos critérios "
           "do UK Brain Bank (bradicinesia + rigidez/tremor/instabilidade postural, "
           "resposta a levodopa); justificar o agonista/adjuvante solicitado.",
}


def gerar_anamnese_lme(dados: str, paciente: str, medicamentos: str,
                       cid10: str) -> str:
    """Anamnese CURTA para o campo 11 do LME, endereçando os critérios do PCDT."""
    criterios = next((v for k, v in CRITERIOS_POR_CID.items()
                      if cid10.upper().startswith(k)), "")
    sistema = (
        "Escreva a ANAMNESE do campo 11 do LME (Laudo de Medicamento Especializado do "
        "SUS): um único parágrafo denso de no máximo 6 linhas, técnico e direto, que "
        "demonstre que o paciente preenche os critérios do PCDT para o medicamento "
        "solicitado. Inclua semiologia, achados objetivos de exames e tratamentos "
        "prévios com doses quando houver. Não invente dados; não mencione o que não "
        "está documentado." + REGRAS_FIXAS +
        (f"\n\nCRITÉRIOS A ENDEREÇAR: {criterios}" if criterios else ""))
    conteudo = (f"Paciente: {paciente}\nMedicamento(s): {medicamentos}\n"
                f"CID-10: {cid10}\n\nDados clínicos:\n{dados}")
    return limpar_texto(_chamar([{"role": "system", "content": sistema},
                                 {"role": "user", "content": conteudo}]))


def gerar_relatorio_alto_custo(dados: str, paciente: str, medicamentos: str,
                               cid10: str, instrucoes: str = "") -> str:
    sistema = _prompt_base("alto_custo") + REGRAS_FIXAS
    if instrucoes.strip():
        sistema += f"\n\nInstruções adicionais do médico: {instrucoes.strip()}"
    criterios = next((v for k, v in CRITERIOS_POR_CID.items()
                      if cid10.upper().startswith(k)), "")
    if criterios:
        sistema += ("\n\nFOCO OBRIGATÓRIO DESTA CONDIÇÃO — o relatório deve endereçar "
                    "explicitamente estes critérios do PCDT: " + criterios)
    conteudo = (f"Paciente: {paciente}\nMedicamento(s) solicitado(s): {medicamentos}\n"
                f"CID-10: {cid10}\n\nDados clínicos:\n{dados}")
    return limpar_texto(_chamar([{"role": "system", "content": sistema},
                                 {"role": "user", "content": conteudo}]))
