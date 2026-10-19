"""Cliente da ponte com o Google Agenda (Apps Script na conta do escritório).

Precisa dos segredos GOOGLE_AGENDA_URL (endereço do App da Web) e
GOOGLE_AGENDA_CHAVE (chave gerada pela função configurar() do script).
Sem eles, as funções devolvem None e o resto do despachante segue normalmente.
"""

import json
import os
import urllib.error
import urllib.request


def configurado():
    return bool(os.environ.get("GOOGLE_AGENDA_URL") and os.environ.get("GOOGLE_AGENDA_CHAVE"))


def _chamar(corpo, timeout=60):
    corpo = dict(corpo, chave=os.environ.get("GOOGLE_AGENDA_CHAVE"))
    req = urllib.request.Request(os.environ["GOOGLE_AGENDA_URL"], data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    # O Apps Script responde com um redirecionamento (302) para o resultado; o urllib segue sozinho.
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode("utf-8", "replace") or "{}")
    if not resp.get("ok"):
        raise RuntimeError(f"Google Agenda recusou: {str(resp.get('erro'))[:150]}")
    return resp


def criar_reuniao(titulo, nome, inicio, fim, descricao, convidado=None):
    """Cria (ou reaproveita) o evento com Meet. Devolve {'id','link','aberta','ja_existia'} ou None."""
    if not configurado():
        return None
    return _chamar({"acao": "criar", "titulo": titulo, "nome": nome,
                    "inicio": inicio.strftime("%Y-%m-%dT%H:%M:00"), "fim": fim.strftime("%Y-%m-%dT%H:%M:00"),
                    "descricao": descricao, "convidado": convidado or ""})


def testar():
    return _chamar({"acao": "teste"}, timeout=30) if configurado() else None
