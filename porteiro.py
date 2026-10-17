"""Porteiro — só acorda o Claude quando chega pedido novo de advogado.

Roda dentro do plantão do despachante. A cada 2 minutos olha, sem IA:
- o privado de cada advogado com o escritório (só a hora da última mensagem;
  baixa a conversa apenas se ela mudou);
- os grupos "Firma 2026" e "AUTOMAÇÃO Firma" (só as mensagens mais recentes).

Se houver mensagem nova de advogado que a secretaria sem IA não resolve
(pedido em texto livre, OK S3, EDITAR R2, comprovante...), grava a hora do
pedido no arquivo sinal.json (ramo "sinal"). As rotinas do Claude (Secretário
geral e Respostas pelo grupo) leem esse arquivo no primeiro passo e encerram na
hora quando não há pedido novo, o que faz a rodada vazia quase não gastar.

O aviso não leva nenhum dado de cliente. O log não leva nome nem telefone.
"""

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
INTERVALO = timedelta(minutes=2)
ESPERA_ENTRE_CHAMADAS = timedelta(minutes=5)   # uma rodada do Claude leva 1 a 3 minutos
GRUPOS = ["claude-grupo-1", "claude-grupo-17"]
PRIVADOS = {"5594992048054": "danielle", "5594991742534": "fernanda", "5524992432455": "lucas"}
RAMO_SINAL, ARQUIVO_SINAL = "sinal", "sinal.json"
# As rotinas leem: https://raw.githubusercontent.com/estevesadvocaciapbs-rgb/despachante-funil/sinal/sinal.json

# Em grupo, só vale como pedido o que fala com o sistema (mesma regra do Secretário geral).
RE_PEDIDO_GRUPO = re.compile(
    r"\b(ok|editar|nao)\s*[rsef]\s*\d|\b(assistente|automacao|annie|claude|ia|escritorio)\b|"
    r"^(agende|agenda|marque|marca|remarque|remarca|cancele|cancela|crie|cria|anote|anota|bloqueie|"
    r"desbloqueie|encerre|encerra|lembre|coloque|coloca|confira|responda|responde|gere|faz|faca|"
    r"lance|lanca|cadastre|cadastra|registre|registra|de baixa|dar baixa)\b")

_estado = {"ultima": None, "desde": None, "visto": {}, "chamado_em": None, "pendente": False}


def _log(msg):
    print(f"[{datetime.now(BRT):%d/%m %H:%M:%S}] porteiro: {msg}", flush=True)


def norm(t):
    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower().strip()


def ler_iso(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def e_advogado_em_grupo(m):
    if m.get("sender") == "CONTACT":
        return any(n in norm(m.get("senderName")) for n in ("danielle", "fernanda", "lucas"))
    if m.get("sender") == "USER":
        return bool(re.match(r"^\*dra?\.?\s*(danielle|fernanda|lucas)", norm(m.get("content"))))
    return False


def resolvido_pelo_codigo(texto, quem):
    """True se a mensagem inteira é comando que a secretaria sem IA executa."""
    import secretaria
    linhas = [l for l in (texto or "").splitlines() if l.strip()]
    if not linhas:
        return True
    if all(secretaria.classificar_linha(l) for l in linhas):
        return True
    if quem == "lucas" and secretaria.ordens_lucas(texto):
        return True
    return False


def pedido_no_privado(m, quem):
    if m.get("sender") != "CONTACT":
        return False
    tipo = m.get("contentType")
    if tipo in ("IMAGE", "DOCUMENT", "PTT", "AUDIO"):
        return True  # comprovante, documento ou áudio transcrito: precisa de IA
    return not resolvido_pelo_codigo(m.get("content"), quem)


def pedido_no_grupo(m):
    if not e_advogado_em_grupo(m):
        return False
    t = norm(m.get("content"))
    return bool(RE_PEDIDO_GRUPO.search(t)) and not resolvido_pelo_codigo(m.get("content"), "")


def novos(msgs, desde, chave):
    """Mensagens depois do último instante já visto nesta chave (ou do início do plantão)."""
    corte = _estado["visto"].get(chave) or desde
    saida = [m for m in msgs if ler_iso(m["createdAt"]) > corte]
    if msgs:
        _estado["visto"][chave] = max(ler_iso(m["createdAt"]) for m in msgs)
    return saida


def _github(metodo, caminho, corpo=None):
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{caminho}", method=metodo,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "despachante-funil"})
    with urllib.request.urlopen(req, timeout=30) as r:
        bruto = r.read().decode()
        return json.loads(bruto) if bruto.strip() else {}


def chamar_claude():
    """Grava o sinal (só a hora do último pedido, sem nenhum dado) no ramo "sinal" do repositório.

    As rotinas do Claude leem esse arquivo no primeiro passo e encerram na hora se não
    houver pedido novo — assim uma rodada sem pedido quase não gasta nada.
    """
    import base64
    if not os.environ.get("GH_TOKEN") or not os.environ.get("GITHUB_REPOSITORY"):
        _log("sem GH_TOKEN/GITHUB_REPOSITORY: não dá para gravar o sinal daqui")
        return False
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    conteudo = json.dumps({"ultimo_pedido": agora.isoformat().replace("+00:00", "Z")}) + "\n"
    try:
        try:
            atual = _github("GET", f"contents/{ARQUIVO_SINAL}?ref={RAMO_SINAL}")
            sha = atual.get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            sha = None
            try:  # primeiro uso: cria o ramo "sinal" a partir do main
                base = _github("GET", "git/ref/heads/main")["object"]["sha"]
                _github("POST", "git/refs", {"ref": f"refs/heads/{RAMO_SINAL}", "sha": base})
            except urllib.error.HTTPError as e2:
                if e2.code != 422:  # 422 = o ramo já existe
                    raise
        corpo = {"message": "sinal: pedido novo", "branch": RAMO_SINAL,
                 "content": base64.b64encode(conteudo.encode()).decode()}
        if sha:
            corpo["sha"] = sha
        _github("PUT", f"contents/{ARQUIVO_SINAL}", corpo)
        return True
    except urllib.error.HTTPError as e:
        _log(f"GitHub recusou o sinal: HTTP {e.code}")
        return False
    except Exception as erro:
        _log(f"sinal não gravado: {type(erro).__name__}")
        return False


def rodada(zaia, agora=None, contagem=None, conversas_lidas=None):
    """conversas_lidas: {telefone: msgs} já baixadas pela secretaria nesta rodada (evita baixar de novo)."""
    agora = agora or datetime.now(timezone.utc)
    contagem = contagem if contagem is not None else {}
    if _estado["desde"] is None:
        _estado["desde"] = agora  # começa a contar do início do plantão
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    achou = 0
    for tel, quem in PRIVADOS.items():
        try:
            msgs = (conversas_lidas or {}).get(tel)
            if msgs is None:
                conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=tel) or {}).get("conversa") or {}
                ultima = conv.get("lastMessageAt")
                if not ultima or ler_iso(ultima) <= (_estado["visto"].get("p" + tel) or _estado["desde"]):
                    continue
                msgs = (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", [])
            achou += sum(1 for m in novos(msgs, _estado["desde"], "p" + tel) if pedido_no_privado(m, quem))
        except Exception as erro:
            _log(f"privado ({quem}) não lido: {type(erro).__name__}")
    for g in GRUPOS:
        try:
            msgs = (zaia.chamar("ler_grupo", grupoId=g, limit=15) or {}).get("mensagens", [])
            achou += sum(1 for m in novos(msgs, _estado["desde"], g) if pedido_no_grupo(m))
        except Exception as erro:
            _log(f"grupo não lido: {type(erro).__name__}")
    if achou:
        _estado["pendente"] = True
    if not _estado["pendente"]:
        return
    if _estado["chamado_em"] and agora - _estado["chamado_em"] < ESPERA_ENTRE_CHAMADAS:
        return  # o Claude acabou de ser chamado; o pedido novo entra na próxima chamada
    if chamar_claude():
        _estado.update(chamado_em=agora, pendente=False)
        contagem["claude_chamado"] = contagem.get("claude_chamado", 0) + 1
        _log("pedido novo de advogado: Claude chamado")
