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
GRUPO_FINANCEIRO = "claude-grupo-18"     # "Financeiro Escritório" (os 3 advogados): pedidos e aprovações F
ARQUIVO_FINANCEIRO = "financeiro.json"   # sinal só da rotina financeira (conversa ali não acorda Secretário/Respostas)
GRUPOS_DESPESAS = [GRUPO_FINANCEIRO, "claude-grupo-17"]  # o 17 fica enquanto houver F antigo aprovado lá
ARQUIVO_DESPESAS = "despesas.json"          # despesas/repasses aprovados ainda não lançados (só códigos)
INTERVALO_DESPESAS = timedelta(minutes=5)
JANELA_DESPESAS = timedelta(days=7)
# "✅ F7 despesa aprovada por Dr. Lucas" / "✅ F7 repasse aprovado por ..." (rotina financeira)
RE_DESP_APROVADA = re.compile(r"✅\s*\*?F(\d+)\*?\s+(?:despesa|repasse)\b[^\n]{0,40}?aprovad", re.I)
# "🧾 F7 de 19/10 lançada no EasyJur" (lançamento noturno pelo Chrome)
RE_DESP_LANCADA = re.compile(r"🧾\s*\*?F(\d+)\*?\s+de\s+(\d{2})/(\d{2})", re.I)
# "💸 *DESPESA F4*", "💰 *LANÇAMENTO F2*", "💰 *BAIXA F7*", "💸 *REPASSE/DESPESA F8*" (rascunhos da rotina financeira)
RE_RASCUNHO = re.compile(r"(?:💸|💰)\s*\*(?:DESPESA|LANÇAMENTO|LANCAMENTO|BAIXA|REPASSE/DESPESA)\s+F(\d+)\*", re.I)
RE_FAVORECIDO = re.compile(r"\b(?:Favorecido|Cliente):\s*([^\n(·]+)")
RE_FALTA = re.compile(r"⚠️\s*falta\s+([^:(\n]+)")
# Aviso da manhã no grupo do financeiro (dias úteis, a partir das 8h): aprovado e não lançado, rascunho parado.
AVISO_PENDENCIAS = "⏰ *Pendências do financeiro"
HORA_AVISO, HORA_AVISO_FIM = 8, 12
ESPERA_RASCUNHO = timedelta(hours=2)    # rascunho mais novo que isto ainda está na conversa
RE_ASSINATURA = re.compile(r"^\s*\*[^*\n]{1,40}\*\s*:[ \t]*\n?")
# As rotinas leem: https://raw.githubusercontent.com/estevesadvocaciapbs-rgb/despachante-funil/sinal/sinal.json

# Em grupo, só vale como pedido o que fala com o sistema (mesma regra do Secretário geral).
RE_PEDIDO_GRUPO = re.compile(
    r"\b(ok|editar|nao)\s*[rsef]\s*\d|\b(assistente|automacao|annie|claude|ia|escritorio)\b|"
    # mensagem programada ao cliente em qualquer ponto da frase ("Quero agendar uma mensagem para a Ana...")
    r"\b(agend|program|envi|mand)\w*\s+(uma\s+|a\s+)?(mensagem|msg)\b|"
    # verbo de ordem no começo da mensagem, de uma linha ou logo depois de um cumprimento ("Bom dia, insira...")
    r"(?:^|[\n.!?,;:]\s*)(agende|agenda|agendar|marque|marca|marcar|remarque|remarca|cancele|cancela|crie|cria|"
    r"criar|anote|anota|bloqueie|desbloqueie|encerre|encerra|lembre|coloque|coloca|ponha|poe|bote|bota|confira|"
    r"responda|responde|gere|faz|faca|lance|lanca|lancar|cadastre|cadastra|cadastrar|registre|registra|"
    r"insira|insere|inserir|inclua|inclui|incluir|adicione|adiciona|mande|manda|envie|envia|avise|avisa|"
    r"informe|informa|confirme|confirma|verifique|verifica|separe|providencie|atualize|atualiza|altere|altera|"
    r"mude|muda|troque|troca|desmarque|desmarca|transfira|encaminhe|encaminha|"
    r"de baixa|dar baixa|da baixa|por favor)\b")

_estado = {"ultima": None, "desde": None, "visto": {}, "chamado_em": None, "pendente": False,
           "fin_chamado_em": None, "fin_pendente": False, "despesas_em": None, "despesas": None,
           "aviso_fin": None}


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
    cmds = secretaria.linhas_de_comando(texto)
    if sum(l.count("\n") + 1 for l, _ in cmds) == len(linhas):  # toda linha é comando (ou texto de CLIENTE 2:)
        # no privado do Dr. Lucas a secretaria só executa CLIENTE; o resto (AGENDAR...) é do Secretário com IA
        if quem != "lucas" or all(c[0].startswith("CLIENTE") for _, c in cmds):
            return True
    if all(re.match(r"^\s*\*?(gravar|oferecer)\b", l, re.I) for l in linhas):
        return True  # "GRAVAR Fulano 19/10 13h" / "OFERECER Fulano 28/10 19h": o despachante faz sozinho
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
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    conteudo = json.dumps({"ultimo_pedido": agora.isoformat().replace("+00:00", "Z")}) + "\n"
    return gravar_no_ramo(ARQUIVO_SINAL, conteudo, "sinal: pedido novo")


def avisar_financeiro():
    """Sinal só para a rotina financeira: mensagem nova de advogado no grupo do financeiro."""
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    conteudo = json.dumps({"ultimo_pedido": agora.isoformat().replace("+00:00", "Z")}) + "\n"
    return gravar_no_ramo(ARQUIVO_FINANCEIRO, conteudo, "sinal: pedido no grupo do financeiro")


ARQUIVO_POSREUNIAO = "posreuniao.json"   # sinal só da rotina pós-reunião (ela só roda inteira quando há novidade)
ESPERA_POSREUNIAO = timedelta(minutes=10)
_pos = {"gravado_em": None, "motivos": set()}


def avisar_posreuniao(motivo, agora=None):
    """Novidade para a pós-reunião (contrato enviado, arquivo de cliente, reunião concluída, lista de documentos,
    tarefa de revisão concluída). Grava só a hora e o tipo — nenhum dado de cliente. No máximo a cada 10 min."""
    agora = (agora or datetime.now(timezone.utc)).replace(microsecond=0)
    _pos["motivos"].add(motivo)
    if _pos["gravado_em"] and agora - _pos["gravado_em"] < ESPERA_POSREUNIAO:
        return False
    conteudo = json.dumps({"ultimo_evento": agora.isoformat().replace("+00:00", "Z"),
                           "motivos": sorted(_pos["motivos"])}) + "\n"
    if gravar_no_ramo(ARQUIVO_POSREUNIAO, conteudo, "sinal: novidade para a pós-reunião"):
        _pos.update(gravado_em=agora, motivos=set())
        _log(f"pós-reunião avisada ({motivo})")
        return True
    return False


RE_DOCUMENTOS_GRUPO = re.compile(r"^\s*\*?documentos\b|documentacao (encerrada|fechada|completa)|documentos completos")


def gravar_no_ramo(arquivo, conteudo, mensagem):
    """Grava um arquivo pequeno (sem dados de cliente) no ramo "sinal" do repositório."""
    import base64
    if not os.environ.get("GH_TOKEN") or not os.environ.get("GITHUB_REPOSITORY"):
        _log("sem GH_TOKEN/GITHUB_REPOSITORY: não dá para gravar o sinal daqui")
        return False
    try:
        try:
            atual = _github("GET", f"contents/{arquivo}?ref={RAMO_SINAL}")
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
        corpo = {"message": mensagem, "branch": RAMO_SINAL,
                 "content": base64.b64encode(conteudo.encode()).decode()}
        if sha:
            corpo["sha"] = sha
        _github("PUT", f"contents/{arquivo}", corpo)
        return True
    except urllib.error.HTTPError as e:
        _log(f"GitHub recusou o sinal: HTTP {e.code}")
        return False
    except Exception as erro:
        _log(f"sinal não gravado: {type(erro).__name__}")
        return False


def despesas_pendentes(msgs, agora):
    """Códigos "F7 de 19/10" com despesa/repasse aprovado e ainda sem "🧾 ... lançada"."""
    aprovadas, lancadas = {}, set()
    for m in msgs:
        texto = m.get("content") or ""
        quando = ler_iso(m["createdAt"])
        if agora - quando > JANELA_DESPESAS:
            continue
        dia = quando.astimezone(BRT).strftime("%d/%m")
        for n in RE_DESP_APROVADA.findall(texto):
            aprovadas[f"F{int(n)} de {dia}"] = True
        for n, d, mes in RE_DESP_LANCADA.findall(texto):
            lancadas.add(f"F{int(n)} de {d}/{mes}")
    return sorted(k for k in aprovadas if k not in lancadas)


def _sem_assinatura(texto):
    return RE_ASSINATURA.sub("", texto or "", count=1)


def _quem(texto):
    m = RE_FAVORECIDO.search(texto)
    return m.group(1).strip(" *") if m else ""


def pendencias_financeiro(msgs, agora):
    """[(chave, linha)] do que está parado no financeiro: despesa aprovada que nenhum lançamento das 22h
    confirmou (sem "🧾") e rascunho F sem resposta de advogado nem decisão (✅/⏭️/🧾) há mais de 2 h."""
    msgs = sorted((m for m in msgs if agora - ler_iso(m["createdAt"]) <= JANELA_DESPESAS),
                  key=lambda m: m["createdAt"])
    itens = []
    aprov = {}
    for m in msgs:
        for n in RE_DESP_APROVADA.findall(m.get("content") or ""):
            aprov[f"F{int(n)} de {ler_iso(m['createdAt']).astimezone(BRT):%d/%m}"] = m
    local = agora.astimezone(BRT)
    ultimas_22h = local.replace(hour=22, minute=0, second=0, microsecond=0)
    if ultimas_22h > local:
        ultimas_22h -= timedelta(days=1)
    for chave in despesas_pendentes(msgs, agora):
        m = aprov.get(chave)
        if not m:
            continue
        quem = _quem(m.get("content") or "")
        if ler_iso(m["createdAt"]) < ultimas_22h:
            estado = "⚠️ aprovada e *ainda não lançada* no EasyJur (já devia ter entrado no lançamento da noite)"
        else:
            estado = "aprovada, *ainda não lançada*: entra no próximo lançamento automático (8h30)"
        itens.append((chave, f"• *{chave}*{' — ' + quem if quem else ''}: {estado}"))
    ultimo = {}
    for i, m in enumerate(msgs):  # o rascunho mais recente de cada F (o "✏️ atualizado" substitui o anterior)
        if m.get("sender") == "CONTACT":
            continue
        for n in RE_RASCUNHO.findall(m.get("content") or ""):
            ultimo[(int(n), f"{ler_iso(m['createdAt']).astimezone(BRT):%d/%m}")] = i
    for (n, dia), i in sorted(ultimo.items(), key=lambda kv: kv[1]):
        m, chave = msgs[i], f"F{n} de {dia}"
        if agora - ler_iso(m["createdAt"]) < ESPERA_RASCUNHO or any(c == chave for c, _ in itens):
            continue
        fechou = re.compile(rf"(?:✅|⏭️|🧾)\s*\*?F{n}\b", re.I)
        respondeu = re.compile(rf"\b(?:ok|editar|nao|não)\s*f\s*{n}\b", re.I)
        if any(fechou.search(x.get("content") or "") if x.get("sender") != "CONTACT"
               else respondeu.search(norm(x.get("content")) or "") for x in msgs[i + 1:]):
            continue
        texto = m.get("content") or ""
        quem = _quem(texto)
        if "⟨ ⟩" in texto:
            falta = RE_FALTA.search(texto)
            estado = (f"esperando dado ({'falta ' + falta.group(1).strip() if falta else 'campo com ⟨ ⟩'}) → "
                      f"*EDITAR F{n}: dado que falta*")
        else:
            estado = f"esperando confirmação → *OK F{n}* · *EDITAR F{n}: ajuste* · *NÃO F{n}*"
        itens.append((chave, f"• *{chave}*{' — ' + quem if quem else ''}: {estado}"))
    return itens


def avisar_pendencias(zaia, msgs, agora):
    """Uma vez por dia útil, a partir das 8h, lista no grupo do financeiro o que está parado."""
    local = agora.astimezone(BRT)
    hoje = local.date()
    if local.weekday() >= 5 or not HORA_AVISO <= local.hour < HORA_AVISO_FIM or _estado["aviso_fin"] == hoje:
        return
    cab = f"{AVISO_PENDENCIAS} — {local:%d/%m}*"
    if any(m.get("sender") != "CONTACT" and _sem_assinatura(m.get("content")).startswith(cab) for m in msgs):
        _estado["aviso_fin"] = hoje
        return
    itens = pendencias_financeiro(msgs, agora)
    _estado["aviso_fin"] = hoje
    if not itens:
        return
    texto = (cab + "\n" + "\n".join(linha for _, linha in itens)
             + "\n_Despesa aprovada é lançada no EasyJur no lançamento automático (8h30, 11h30, 15h30 e 22h30) "
             "e confirmada aqui com 🧾. "
             "Se algo da lista já foi resolvido, responda o código (ex.: NÃO F4) ou ignore._")
    try:
        zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=GRUPO_FINANCEIRO, texto=texto)
        _log(f"aviso de pendências do financeiro: {len(itens)} item(ns)")
    except Exception as erro:
        _estado["aviso_fin"] = None  # tenta de novo na próxima volta
        _log(f"aviso de pendências não enviado: {type(erro).__name__}")


def atualizar_despesas(zaia, agora):
    """A cada 5 min confere os grupos do financeiro e grava despesas.json só quando a lista muda."""
    if _estado["despesas_em"] and agora - _estado["despesas_em"] < INTERVALO_DESPESAS:
        return
    _estado["despesas_em"] = agora
    msgs = []
    try:
        for g in GRUPOS_DESPESAS:
            msgs += (zaia.chamar("ler_grupo", grupoId=g, limit=100) or {}).get("mensagens", [])
    except Exception as erro:
        _log(f"despesas: grupo não lido: {type(erro).__name__}")
        return
    avisar_pendencias(zaia, msgs, agora)
    pend = despesas_pendentes(msgs, agora)
    if pend == _estado["despesas"]:
        return
    conteudo = json.dumps({"pendentes": pend, "atualizado": agora.replace(microsecond=0)
                           .isoformat().replace("+00:00", "Z")}, ensure_ascii=False) + "\n"
    if gravar_no_ramo(ARQUIVO_DESPESAS, conteudo, "despesas aprovadas a lançar"):
        _estado["despesas"] = pend
        _log(f"despesas a lançar: {len(pend)}")


def rodada(zaia, agora=None, contagem=None, conversas_lidas=None):
    """conversas_lidas: {telefone: msgs} já baixadas pela secretaria nesta rodada (evita baixar de novo)."""
    agora = agora or datetime.now(timezone.utc)
    contagem = contagem if contagem is not None else {}
    if _estado["desde"] is None:
        _estado["desde"] = agora  # começa a contar do início do plantão
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    atualizar_despesas(zaia, agora)
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
            recentes = novos(msgs, _estado["desde"], g)
            achou += sum(1 for m in recentes if pedido_no_grupo(m))
            if any(e_advogado_em_grupo(m) and RE_DOCUMENTOS_GRUPO.search(norm(_sem_assinatura(m.get("content"))))
                   for m in recentes):
                avisar_posreuniao("lista ou encerramento de documentos no grupo", agora)
        except Exception as erro:
            _log(f"grupo não lido: {type(erro).__name__}")
    try:  # grupo do financeiro: qualquer mensagem de advogado (pedido, comprovante, OK F3) acorda só o financeiro
        msgs = (zaia.chamar("ler_grupo", grupoId=GRUPO_FINANCEIRO, limit=15) or {}).get("mensagens", [])
        if any(e_advogado_em_grupo(m) for m in novos(msgs, _estado["desde"], GRUPO_FINANCEIRO)):
            _estado["fin_pendente"] = True
    except Exception as erro:
        _log(f"grupo do financeiro não lido: {type(erro).__name__}")
    if _estado["fin_pendente"] and not (_estado["fin_chamado_em"]
                                        and agora - _estado["fin_chamado_em"] < ESPERA_ENTRE_CHAMADAS):
        if avisar_financeiro():
            _estado.update(fin_chamado_em=agora, fin_pendente=False)
            contagem["financeiro_chamado"] = contagem.get("financeiro_chamado", 0) + 1
            _log("pedido no grupo do financeiro: rotina financeira chamada")
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
