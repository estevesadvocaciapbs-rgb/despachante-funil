"""Conversas do dia (pedido do Dr. Lucas em 27/11/2026): todo dia às 19h, um pequeno banco de dados das conversas
de WhatsApp do escritório numa planilha do Google ("Conversas WhatsApp – banco diário"), para o painel de gestão.

Uma linha por conversa por dia, SÓ com números e horários: quem é (nome, telefone, lead / cliente ativo / outro),
quantas mensagens de cada lado, quantas vezes a conversa foi retomada, 1ª e última mensagem, quem iniciou, se ficou
sem resposta e quem respondeu (pela assinatura). O texto das mensagens nunca é guardado.

Sem IA. Fontes: Za.Ia (listar_conversas + ler_conversa) e EasyJur (processos ativos; o telefone de cada cliente fica
num cache na própria planilha para poupar a cota). Destino: "Ponte Planilha" (ponte_planilha.gs), segredos
GOOGLE_PLANILHA_URL e GOOGLE_PLANILHA_CHAVE.

Cada execução grava HOJE (até a hora da execução) e regrava ONTEM inteiro, para pegar o que veio depois das 19h.
Regravar um dia troca as linhas dele, então repetir a execução não duplica nada.

Repositório PÚBLICO: o log mostra só contagens, nunca nome, telefone ou conteúdo.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

import despachante
import telefones
from funil_semanal import _z

BRT = timezone(timedelta(hours=-3))
SILENCIO_RETOMADA = timedelta(minutes=60)  # mensagem depois de 1 h parada = conversa retomada
DIAS_LEAD = 60  # conversa aberta há até 60 dias, sem processo ativo e sem etiqueta Cliente/Reclamada = lead
MAX_PESSOAS_NOVAS = 60  # get_pessoa por execução (o resto entra no cache nos dias seguintes)
STATUS = (None, "OPEN", "ASSIGNED", "CLOSED")  # a listagem sem status não garante trazer as encerradas

COLUNAS = ["data", "id_conversa", "id_contato_zaia", "nome", "telefone", "tipo", "id_pessoa_easyjur",
           "processos_ativos", "msgs_cliente", "msgs_equipe", "msgs_annie", "total_msgs", "retomadas",
           "primeira_msg", "ultima_msg", "quem_iniciou", "sem_resposta", "minutos_sem_resposta", "quem_respondeu",
           "msgs_por_pessoa", "gravado_em"]


def _log(msg):
    despachante.log(f"[conversas-dia] {msg}")


def iso(t):
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ler_iso(txt):
    return datetime.fromisoformat((txt or "").replace("Z", "+00:00"))


def inicio_do_dia(d):
    return datetime(d.year, d.month, d.day, tzinfo=BRT)


# ---------------------------------------------------------------- Za.Ia

def conversas_do_periodo(zaia, ini, fim):
    """Conversas com movimento entre ini e fim, sem repetir (a mesma conversa pode vir em mais de um status)."""
    vistas = {}
    for status in STATUS:
        offset = 0
        while offset < 2000:
            r = _z(zaia, "listar_conversas", limit=100, offset=offset, status=status,
                   periodo={"inicio": iso(ini), "fim": iso(fim)}) or {}
            itens = r.get("atendimentos") or r.get("conversas") or []
            for a in itens:
                cid = (a.get("conversa") or {}).get("id") or a.get("id")
                if cid and cid not in vistas:
                    vistas[cid] = a
            offset += 100
            if len(itens) < 100 or offset >= int(r.get("total") or 0):
                break
    return list(vistas.values())


def etiquetados(zaia, etiqueta):
    """Telefones com a etiqueta (Cliente / Reclamada), para separar cliente, parte contrária e lead."""
    tels, offset = set(), 0
    while offset < 2000:
        r = _z(zaia, "listar_contatos", etiqueta=etiqueta, limit=100, offset=offset) or {}
        itens = r.get("contatos") or []
        tels |= {telefones.whatsapp(c.get("phone")) for c in itens}
        offset += 100
        if len(itens) < 100:
            break
    return tels - {None}


# ---------------------------------------------------------------- quem escreveu

def autor(m):
    """'cliente', 'Annie' ou o nome curto de quem da equipe assinou a mensagem."""
    if m.get("sender") == "CONTACT":
        return "cliente"
    if m.get("sender") == "AGENT":
        return "Annie"
    txt = m.get("content") or ""
    assin = despachante.RE_ASSINATURA_HUMANA.match(txt)
    nome = assin.group(1).strip() if assin else (m.get("senderName") or "").strip()
    if not nome or despachante.sem_acento(nome) in ("automacao", "ia"):
        return "Annie" if txt.lstrip().startswith("*Annie") else "equipe (sem assinatura)"
    if "annie" in despachante.sem_acento(nome):
        return "Annie"
    adv = despachante.advogado_por_nome(nome)
    return adv["curto"] if adv else nome.title()


def resumo_do_dia(msgs, ini, fim):
    """Contagens de uma conversa entre ini e fim (só números e horários). None se não houve mensagem."""
    do_dia = sorted((m for m in msgs if m.get("createdAt") and ini <= ler_iso(m["createdAt"]) < fim),
                    key=lambda m: m["createdAt"])
    do_dia = [m for m in do_dia if m.get("contentType") != "SYSTEM"]
    if not do_dia:
        return None
    autores = [autor(m) for m in do_dia]
    horas = [ler_iso(m["createdAt"]) for m in do_dia]
    por_pessoa = {}
    for a in autores:
        if a != "cliente":
            por_pessoa[a] = por_pessoa.get(a, 0) + 1
    retomadas = sum(1 for a, b in zip(horas, horas[1:]) if b - a >= SILENCIO_RETOMADA)
    sem_resposta = autores[-1] == "cliente"
    espera = 0
    if sem_resposta:
        k = len(autores) - 1
        while k > 0 and autores[k - 1] == "cliente":
            k -= 1
        espera = int((fim - horas[k]).total_seconds() // 60)  # fim já vem limitado à hora da execução
    annie = por_pessoa.get("Annie", 0)
    equipe = sum(v for k, v in por_pessoa.items() if k != "Annie")
    return {
        "msgs_cliente": autores.count("cliente"), "msgs_equipe": equipe, "msgs_annie": annie,
        "total_msgs": len(autores), "retomadas": retomadas,
        "primeira_msg": horas[0].astimezone(BRT).strftime("%H:%M"),
        "ultima_msg": horas[-1].astimezone(BRT).strftime("%H:%M"),
        "quem_iniciou": "cliente" if autores[0] == "cliente" else "escritório",
        "sem_resposta": 1 if sem_resposta else 0, "minutos_sem_resposta": max(espera, 0),
        "quem_respondeu": ", ".join(sorted(por_pessoa, key=lambda k: -por_pessoa[k])),
        "msgs_por_pessoa": "; ".join(f"{k} {v}" for k, v in sorted(por_pessoa.items(), key=lambda kv: -kv[1])),
    }


# ---------------------------------------------------------------- EasyJur: clientes com processo ativo

def clientes_ativos(ej, ponte):
    """{telefone: (id_pessoa, nº de processos ativos)}. Telefone de pessoa nova sai do get_pessoa e entra no cache."""
    contagem = {}
    for pagina in range(1, 21):
        r = ej.chamar("list_processos", status="1", page_size=100, page=pagina) or {}
        for p in r.get("data") or []:
            if p.get("id_cliente"):
                contagem[str(p["id_cliente"])] = contagem.get(str(p["id_cliente"]), 0) + 1
        if pagina >= int((r.get("meta") or {}).get("total_pages") or 1):
            break
    cache = ponte("ler_clientes").get("clientes") or {}
    novos = {}
    for pid in [p for p in contagem if p not in cache][:MAX_PESSOAS_NOVAS]:
        try:
            pessoa = (ej.chamar("get_pessoa", pessoa_id=int(pid)) or {}).get("data") or {}
        except despachante.OrcamentoEasyJur:
            break
        novos[pid] = telefones.do_cadastro(pessoa) or ""
    if novos:
        ponte("gravar_clientes", clientes=novos)
        cache.update(novos)
    faltam = sum(1 for p in contagem if p not in cache)
    por_tel = {}
    for pid, n in contagem.items():
        tel = telefones.whatsapp(cache.get(pid))
        if tel:
            por_tel[tel] = (pid, n)
    return por_tel, faltam


def tipo(tel, conversa, ativos, com_cliente, reclamadas, agora):
    if tel in ativos:
        return "cliente ativo"
    if tel in com_cliente or tel in reclamadas:
        return "outro"
    criada = conversa.get("createdAt")
    if criada and agora - ler_iso(criada) <= timedelta(days=DIAS_LEAD):
        return "lead"
    return "outro"


# ---------------------------------------------------------------- ponte com a planilha

def ponte_padrao(acao, **corpo):
    url, chave = os.environ.get("GOOGLE_PLANILHA_URL"), os.environ.get("GOOGLE_PLANILHA_CHAVE")
    if not (url and chave):
        raise RuntimeError("segredos GOOGLE_PLANILHA_URL / GOOGLE_PLANILHA_CHAVE não configurados")
    req = urllib.request.Request(url, data=json.dumps(dict(corpo, acao=acao, chave=chave)).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:  # o Apps Script responde com 302; o urllib segue
        resp = json.loads(r.read().decode("utf-8", "replace") or "{}")
    if not resp.get("ok"):
        raise RuntimeError(f"planilha recusou: {str(resp.get('erro'))[:150]}")
    return resp


# ---------------------------------------------------------------- rodada

def linhas_dos_dias(zaia, ej, ponte, dias, agora):
    """Linhas (listas na ordem de COLUNAS) de cada dia em `dias`, com uma leitura só por conversa."""
    ini = inicio_do_dia(min(dias))
    fim = min(inicio_do_dia(max(dias)) + timedelta(days=1), agora)
    conversas = conversas_do_periodo(zaia, ini, fim)
    fora = despachante.EQUIPE | {a["tel"] for a in despachante.ADVOGADOS} | {despachante.TEL_ERROS}
    ativos, faltam = clientes_ativos(ej, ponte)
    com_cliente, reclamadas = etiquetados(zaia, "Cliente"), etiquetados(zaia, "Reclamada")
    gravado = agora.astimezone(BRT).strftime("%Y-%m-%d %H:%M")
    linhas, conta = [], {"equipe/grupo": 0, "sem mensagem": 0, "erro": 0}
    for a in conversas:
        conv = a.get("conversa") or {}
        tel = telefones.whatsapp(a.get("phone") or (a.get("contact") or {}).get("phone"))
        if not tel or tel in fora or "@g.us" in str(a.get("phone") or ""):
            conta["equipe/grupo"] += 1
            continue
        try:
            msgs = (_z(zaia, "ler_conversa", conversaId=conv.get("id")) or {}).get("messages") or []
        except Exception as e:  # uma conversa ilegível não derruba o dia
            conta["erro"] += 1
            _log(f"conversa não lida: {type(e).__name__}")
            continue
        for d in dias:
            r = resumo_do_dia(msgs, inicio_do_dia(d), min(inicio_do_dia(d) + timedelta(days=1), agora))
            if not r:
                conta["sem mensagem"] += 1
                continue
            pid, nproc = ativos.get(tel, ("", 0))
            r.update(data=d.isoformat(), id_conversa=conv.get("id") or "",
                     id_contato_zaia=(a.get("contact") or {}).get("id") or "",
                     nome=(a.get("contact") or {}).get("name") or a.get("name") or "", telefone=tel,
                     tipo=tipo(tel, conv, ativos, com_cliente, reclamadas, agora), id_pessoa_easyjur=pid,
                     processos_ativos=nproc, gravado_em=gravado)
            linhas.append([r[c] for c in COLUNAS])
    return linhas, len(conversas), conta, faltam


def rodada(zaia, ej, ponte=ponte_padrao, agora=None, dias=None, gravar=True):
    agora = agora or datetime.now(timezone.utc)
    hoje = agora.astimezone(BRT).date()
    dias = sorted(dias or [hoje - timedelta(days=1), hoje])
    linhas, n_conv, conta, faltam = linhas_dos_dias(zaia, ej, ponte, dias, agora)
    for d in dias:
        do_dia = [l for l in linhas if l[0] == d.isoformat()]
        col = COLUNAS.index
        _log(f"{d:%d/%m}: {len(do_dia)} conversa(s), {sum(l[col('sem_resposta')] for l in do_dia)} sem resposta, "
             f"{sum(1 for l in do_dia if l[col('tipo')] == 'lead')} lead(s), "
             f"{sum(1 for l in do_dia if l[col('tipo')] == 'cliente ativo')} cliente(s) ativo(s), "
             f"{sum(l[col('total_msgs')] for l in do_dia)} mensagem(ns)")
    _log(f"listadas {n_conv}; fora (equipe/grupo) {conta['equipe/grupo']}; não lidas {conta['erro']}; "
         f"clientes ativos sem telefone no cache ainda: {faltam}")
    if gravar:
        r = ponte("gravar_dia", colunas=COLUNAS, dias=[d.isoformat() for d in dias], linhas=linhas)
        _log(f"gravado na planilha: {r.get('linhas')} linha(s); total na planilha {r.get('total')}")
    return linhas


def main(argv):
    simular = "--simular" in argv
    if not simular and not (os.environ.get("GOOGLE_PLANILHA_URL") and os.environ.get("GOOGLE_PLANILHA_CHAVE")):
        _log("planilha ainda não configurada (segredos GOOGLE_PLANILHA_URL / GOOGLE_PLANILHA_CHAVE); nada a fazer")
        return
    zaia = despachante.MCP(despachante.ZAIA_URL, os.environ.get("ZAIA_TOKEN"), "Za.Ia")
    ej = despachante.MCP(despachante.EASYJUR_URL, os.environ.get("EASYJUR_TOKEN"), "EasyJur")
    dias = [date.fromisoformat(a) for a in argv if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a)]
    agora = datetime.now(timezone.utc)
    if dias and max(dias) < agora.astimezone(BRT).date():
        agora_dia = inicio_do_dia(max(dias)) + timedelta(days=1)  # dia passado: janela inteira
        agora = min(agora, agora_dia)
    try:
        rodada(zaia, ej, agora=agora, dias=dias or None, gravar=not simular,
               ponte=ponte_padrao if not simular or os.environ.get("GOOGLE_PLANILHA_URL")
               else (lambda acao, **_: {"clientes": {}}))
    except Exception as e:
        _log(f"falhou: {type(e).__name__}: {e}")
        marca = f"{agora.astimezone(BRT):%d/%m}"
        if not simular and not despachante.ja_avisou_lucas(zaia, ("CONVERSAS DO DIA", marca)):
            despachante.avisar_lucas(zaia, f"🛠️ *CONVERSAS DO DIA {marca} — planilha não atualizada*\n"
                                     f"{type(e).__name__}: {str(e)[:200]}\nHá nova tentativa automática em 20 min.")
        raise
    finally:
        _log(f"chamadas ao EasyJur: {despachante.ESTADO_EJ['chamadas']}")


if __name__ == "__main__":
    main(sys.argv[1:])
