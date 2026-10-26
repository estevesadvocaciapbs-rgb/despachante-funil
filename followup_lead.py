"""Follow-up de lead que parou de responder na triagem — sem IA (pedido da usuária em 26/10/2026, caso Edson).

Roda dentro do plantão do despachante, a cada 15 minutos. Olha as conversas de LEADS NOVOS (conversa aberta
nos últimos 14 dias, ainda com a Annie — status OPEN —, sem ninguém da equipe escrevendo nos últimos 30 dias)
em que a última mensagem é uma PERGUNTA da Annie e o lead sumiu. Então a Annie chama de novo:

  F1 — 1 hora depois da pergunta ("Ainda está por aí?")
  F2 — no dia seguinte (20 horas depois do F1)
  F3 — 3 dias depois do F2 (avisa que é a última mensagem)

Só manda das 8h às 19h59 (Belém), todos os dias. Quando o lead responde, a Annie continua o roteiro
(ativarIaAoResponder). Não manda: se a pergunta da Annie tem mais de 3 dias e ninguém chamou ainda (lead
antigo), se o lead já recebeu oferta de horários (essa parte é da oferta/resgate), se há mensagem agendada
para ele, ou depois do F3. Privacidade: o log não leva nome nem telefone.
"""

import re
from datetime import datetime, timedelta, timezone

INTERVALO = timedelta(minutes=15)
JANELA_LISTA = timedelta(days=5)          # conversas com movimento nos últimos 5 dias
CONVERSA_NOVA = timedelta(days=14)        # lead novo: conversa criada há no máximo 14 dias
ESPERA_F1 = timedelta(hours=1)
ESPERA_F2 = timedelta(hours=20)
ESPERA_F3 = timedelta(days=3)
F1_ATE = timedelta(days=3)                # pergunta mais velha que isso sem follow-up: não começa agora
HORAS = range(8, 20)
MARCAS = ("Ainda está por aí?", "Passando para saber se você ainda precisa de ajuda",
          "Esta é a minha última mensagem por aqui")
_estado = {"ultima": None}


def _log(msg):
    print(f"[{datetime.now(timezone(timedelta(hours=-3))):%d/%m %H:%M:%S}] follow-up: {msg}", flush=True)


def e_annie(m):
    return m.get("sender") != "CONTACT" and (m.get("content") or "").lstrip().startswith("*Annie*")


def texto_followup(n, nome, d):
    pn = d.primeiro_nome(nome or "")
    oi = f"Oi, {pn}!" if pn else "Oi!"
    return {
        1: f"{oi} {MARCAS[0]} 😊 Pra eu te ajudar com o seu caso, é só me responder a última pergunta, "
           "por escrito ou por áudio. Pode ser?",
        2: f"{oi} {MARCAS[1]} com o seu caso. Quando puder, me conta o que está acontecendo que eu te direciono "
           "para o advogado certo. Pode ser?",
        3: f"{oi} {MARCAS[2]}. Se ainda quiser orientação sobre o seu caso, é só me responder quando puder, "
           "que eu continuo daqui. Combinado?",
    }[n]


def proximo(msgs, agora, d):
    """(n, quando) do próximo follow-up, ou (None, motivo)."""
    if not msgs:
        return None, "sem mensagens"
    if any(d.MARCA_OFERTA in (m.get("content") or "") for m in msgs):
        return None, "já recebeu oferta de horários"
    if any(d.escrita_por_humano(m) and agora - d.ler_iso(m["createdAt"]) <= timedelta(days=30) for m in msgs):
        return None, "equipe atendendo"
    ultima = msgs[-1]
    if ultima.get("sender") == "CONTACT":
        return None, "lead respondeu (a Annie continua)"
    # última fala do lead e o que veio depois dela
    i_lead = max((i for i, m in enumerate(msgs) if m.get("sender") == "CONTACT"), default=-1)
    depois = msgs[i_lead + 1:]
    feitos = [m for m in depois if any(k in (m.get("content") or "") for k in MARCAS)]
    perguntas = [m for m in depois if e_annie(m) and "?" in (m.get("content") or "")
                 and not any(k in (m.get("content") or "") for k in MARCAS)]
    if not perguntas:
        return None, "a Annie não fez pergunta (ou encerrou)"
    n = len(feitos)
    if n >= 3:
        return None, "fim"
    if n == 0:
        base = d.ler_iso(perguntas[-1]["createdAt"])
        if agora - base > F1_ATE:
            return None, "pergunta antiga demais"
        return 1, base + ESPERA_F1
    ult = d.ler_iso(feitos[-1]["createdAt"])
    return n + 1, ult + (ESPERA_F2 if n == 1 else ESPERA_F3)


def rodada(zaia, agora, contagem, d, pendentes=()):
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    local = agora.astimezone(d.BRT)
    if local.hour not in HORAS:
        return
    lista = zaia.chamar("listar_conversas", limit=100, status="OPEN", periodo={
        "inicio": (agora - JANELA_LISTA).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "fim": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}) or {}
    pend = {p.get("contactId") for p in pendentes}
    for at in lista.get("atendimentos", []):
        conv = at.get("conversa") or {}
        tel = (at.get("phone") or "").strip()
        contato = (at.get("contact") or {}).get("id")
        if (conv.get("status") != "OPEN" or not tel or tel in d.EQUIPE or not conv.get("id") or contato in pend
                or not conv.get("createdAt") or agora - d.ler_iso(conv["createdAt"]) > CONVERSA_NOVA):
            continue
        ultima_msg = conv.get("lastMessageAt")
        if ultima_msg and agora - d.ler_iso(ultima_msg) < ESPERA_F1:
            continue  # conversa andando: nem lê
        msgs = sorted((zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []),
                      key=lambda m: m["createdAt"])
        n, quando = proximo(msgs, agora, d)
        if n is None or quando > agora:
            continue
        nome = (at.get("contact") or {}).get("name") or at.get("name") or ""
        contagem["followups_lead"] = contagem.get("followups_lead", 0) + 1
        if d.DRY_RUN:
            _log(f"[simulação] mandaria o F{n}")
            continue
        hora = (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:00.000Z")
        zaia.chamar("agendar_mensagem", contatoId=contato, conversaId=conv["id"], mensagem=texto_followup(n, nome, d),
                    dataHora=hora, assinatura="ia", ativarIaAoResponder=True)
        _log(f"lead parado na triagem: F{n} agendado")
