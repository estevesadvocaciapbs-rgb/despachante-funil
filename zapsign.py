"""Ligação com o ZapSign (24/11/2026): gera o kit trabalhista do reclamante já preenchido e confere a assinatura.

Só usa a biblioteca padrão do Python, para rodar igual no GitHub e, depois da migração, no VPS.
- ZAPSIGN_TOKEN: chave da API (segredo; nunca vai para log).
- ZAPSIGN_AMBIENTE: "sandbox" (padrão, sem validade jurídica) ou "producao".
- ZAPSIGN_MODELO_RECLAMANTE: id do modelo; sem ele, usa o do ambiente de teste.
Privacidade: o repositório é público. O log leva só o id do documento e o status, nunca nome, CPF ou link.
"""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date

BASES = {"sandbox": "https://sandbox.api.zapsign.com.br/api/v1",
         "producao": "https://api.zapsign.com.br/api/v1"}
MODELO_TESTE = "08035446-f7c9-4dd1-a502-3b7e00bdf38b"  # "Kit Trabalhista - Empregado/Reclamante" no sandbox
QTD_SM_TUTELA_PADRAO = "1"  # decisão da usuária em 24/11
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
# campos do modelo que a Annie precisa colher; os demais o robô preenche
OBRIGATORIOS = ["NOME_COMPLETO", "NACIONALIDADE", "ESTADO_CIVIL", "PROFISSAO", "RG", "ORGAO_EMISSOR", "CPF",
                "ENDERECO_COMPLETO", "CIDADE", "UF", "CEP", "PARTE_CONTRARIA"]


class ErroZapSign(Exception):
    pass


def ativo():
    return bool(os.environ.get("ZAPSIGN_TOKEN"))


def _base():
    return BASES.get(os.environ.get("ZAPSIGN_AMBIENTE", "sandbox"), BASES["sandbox"])


def _chamar(metodo, caminho, corpo=None, abrir=urllib.request.urlopen):
    cab = {"Authorization": f"Bearer {os.environ['ZAPSIGN_TOKEN']}", "Content-Type": "application/json"}
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(_base() + caminho, data=dados, headers=cab, method=metodo)
    try:
        with abrir(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise ErroZapSign(f"HTTP {e.code} em {caminho.split('/')[1]}") from None
    except (urllib.error.URLError, OSError) as e:
        raise ErroZapSign(f"sem conexão ({type(e).__name__})") from None


def data_extenso(d):
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _so_digitos(s):
    return re.sub(r"\D", "", s or "")


def faltando(cliente):
    """Campos obrigatórios que a Annie ainda não colheu."""
    return [c for c in OBRIGATORIOS if not str(cliente.get(c) or "").strip()]


def criar_kit(cliente, tel, ref, hoje=None, abrir=urllib.request.urlopen):
    """Cria o kit no ZapSign. cliente: dict com os campos do modelo; tel: 55DDDNÚMERO; ref: id nosso (external_id).
    Devolve {"doc": token do documento, "link": link de assinatura do cliente}. O ZapSign não envia nada:
    o link sai pela Za.Ia, com a assinatura da Annie."""
    falta = faltando(cliente)
    if falta:
        raise ErroZapSign("faltam campos: " + ", ".join(falta))
    tel = _so_digitos(tel)
    numero = tel[2:] if tel.startswith("55") and len(tel) >= 12 else tel
    campos = dict(cliente)
    campos.setdefault("QTD_SM_TUTELA", QTD_SM_TUTELA_PADRAO)
    campos["TELEFONE_CLIENTE"] = f"({numero[:2]}) {numero[2:]}" if len(numero) >= 10 else numero
    campos["EMAIL_CLIENTE"] = (campos.get("EMAIL_CLIENTE") or "").strip() or "não informado"
    campos["DATA"] = data_extenso(hoje or date.today())
    corpo = {
        "template_id": os.environ.get("ZAPSIGN_MODELO_RECLAMANTE") or MODELO_TESTE,
        "signer_name": campos["NOME_COMPLETO"].strip(),
        "signer_phone_country": "55",
        "signer_phone_number": numero,
        "send_automatic_email": False,
        "send_automatic_whatsapp": False,
        "lang": "pt-br",
        "external_id": str(ref),
        "data": [{"de": "{{%s}}" % k, "para": str(v).strip()} for k, v in campos.items()],
    }
    r = _chamar("POST", "/models/create-doc/", corpo, abrir)
    signatarios = r.get("signers") or []
    if not r.get("token") or not signatarios or not signatarios[0].get("sign_url"):
        raise ErroZapSign("resposta sem documento ou sem link")
    return {"doc": r["token"], "link": signatarios[0]["sign_url"]}


def situacao(doc, abrir=urllib.request.urlopen):
    """'pending', 'signed' ou 'refused' (como o ZapSign devolve), mais o link do PDF assinado quando houver."""
    r = _chamar("GET", f"/docs/{doc}/", None, abrir)
    return {"status": r.get("status"), "pdf": r.get("signed_file")}
