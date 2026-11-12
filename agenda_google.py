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


def procurar_pasta(nome, area=None):
    """Pastas Processos › ÁREA › Nome com todas as palavras de `nome`: [{'id','caminho'}] ou None sem ponte."""
    if not configurado():
        return None
    return _chamar({"acao": "procurar_pasta", "nome": nome, "area": area or ""}, timeout=120).get("candidatos", [])


def guardar_arquivos(tel, de, ate, nome, area=None, escolha=None, criar=False, nome_pasta=""):
    """Move os arquivos do telefone (Mídias - Whatsapp, criados entre de e ate) para Docs de Prova do cliente."""
    if not configurado():
        return None
    from datetime import timezone
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    de, ate = de.astimezone(timezone.utc), ate.astimezone(timezone.utc)
    return _chamar({"acao": "guardar", "tel": tel, "de": de.strftime(fmt), "ate": ate.strftime(fmt), "nome": nome,
                    "area": area or "", "escolha": escolha or 0, "criar": bool(criar), "nome_pasta": nome_pasta},
                   timeout=180)


def testar():
    return _chamar({"acao": "teste"}, timeout=30) if configurado() else None
