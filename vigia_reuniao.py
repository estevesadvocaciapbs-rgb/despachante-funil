"""Vigia das mensagens agendadas de reunião — sem IA (pedido da usuária em 24/11/2026).

Problema: os lembretes ao cliente (8h do dia e 1 hora antes) e a confirmação com o link são agendados na Za.Ia
na hora em que a reunião é gravada, e nada os cancelava depois. Quem desmarcava, era desmarcado no EasyJur ou
remarcava recebia mesmo assim "lembrar do seu atendimento de hoje" e "Podemos confirmar sua presença?"; sem
resposta, o resgate ainda mandava "Senti sua falta" (19 a 23/11).

A cada 20 minutos (das 6h às 22h), para cada lembrete/confirmação de reunião ainda PENDENTE, confere o
atendimento no EasyJur e a conversa e CANCELA a mensagem quando:
  1. o atendimento daquele dia e hora está Cancelado (S) no EasyJur e não há outro vivo no mesmo horário
     (a duplicata cancelada pelo auditor não conta: vale o atendimento vivo);
  2. não há atendimento vivo naquele horário, mas há outro atendimento vivo do mesmo cliente em outra data
     (remarcada: os lembretes da data nova são criados na gravação nova);
  3. o cliente escreveu, depois da confirmação e antes da reunião, que não vai poder / quer desmarcar ou
     remarcar, e ninguém confirmou a reunião de novo depois disso.
Sem atendimento achado no EasyJur (nem pelo telefone, nem pelo nome), não cancela nada: na dúvida, mantém.
A equipe recebe um aviso no grupo (uma vez por reunião). No caso 3 o aviso pede para marcar Cancelado no
EasyJur, porque o despachante não desmarca a agenda do advogado sozinho por uma frase do cliente.

Privacidade: o log não leva nome nem telefone.
"""

import re
from datetime import datetime, timedelta, timezone

A_CADA = timedelta(minutes=20)
HORAS = range(6, 23)
TITULO = "🚫 *LEMBRETES CANCELADOS"
RE_E_LEMBRETE = re.compile(r"lembrar do seu atendimento de hoje|confirmar nosso atendimento de hoje|"
                           r"est[aá] confirmada para|Este [eé] o link do seu atendimento")
RE_DATA_HORA = re.compile(r"(\d{2})/(\d{2}),?\s+[àáa]s\s+(\d{1,2})h(\d{2})")
RE_HORA = re.compile(r"\b[àáa]s\s+(\d{1,2})h(\d{2})")
RE_TEL = re.compile(r"\b55\d{10,11}\b")
# o cliente desmarcando (texto já sem acento); "não consigo entrar no link" é problema técnico, não desmarque
RE_DESMARCA = re.compile(
    r"desmarc|cancel|remarc|adiar|nao vou (poder|conseguir|mais|participar|comparecer)|nao poderei|"
    r"nao (vai|vou) dar\b|nao (consigo|posso) (ir|participar|comparecer|mais|hoje|amanha|nesse|neste|nessa|nesta)|"
    r"imprevisto|outro dia|outra data|surgiu (um|uma)")
RE_TECNICO = re.compile(r"\blink\b|entrar|acessar|camera|microfone|audio|internet|sinal")
RE_MANTEM = re.compile(r"vou sim|estarei (la|ai|presente)|pode manter|mantem|confirmad|confirmo|consigo sim|"
                       r"\bvou estar\b|tudo certo")
_estado = {"ultima": None, "avisados": set()}


def _log(msg):
    print(f"[{datetime.now(timezone(timedelta(hours=-3))):%d/%m %H:%M:%S}] vigia de reunião: {msg}", flush=True)


def todos_pendentes(zaia, paginas=10):
    """Todas as mensagens PENDENTES da Za.Ia (antes era só a primeira página de 50: contato com lembrete
    na página 2 parecia não ter nada agendado e recebia resgate/follow-up por cima)."""
    todos, offset = [], 0
    for _ in range(paginas):
        r = zaia.chamar("listar_agendamentos", status="PENDING", limit=100, offset=offset) or {}
        todos += r.get("agendamentos", [])
        if not r.get("temMais") or r.get("proximoOffset") is None:
            break
        offset = r["proximoOffset"]
    return todos


def texto_de(p):
    return p.get("content") or " ".join(x.get("texto") or "" for x in p.get("mensagens") or [])


def slot_do_lembrete(p, d):
    """Início da reunião (Belém) citado num lembrete/confirmação pendente, ou None se não for de reunião."""
    txt = texto_de(p)
    if not RE_E_LEMBRETE.search(txt) or not p.get("scheduledAt"):
        return None
    sai = d.ler_iso(p["scheduledAt"]).astimezone(d.BRT)
    m = RE_DATA_HORA.search(txt)
    if m:
        dd, mm, hh, mi = (int(x) for x in m.groups())
        ano = sai.year + (1 if mm < sai.month else 0)
        return datetime(ano, mm, dd, hh, mi, tzinfo=d.BRT)
    m = RE_HORA.search(txt)
    if m and "hoje" in txt:
        return sai.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    return None


def telefone_de(p):
    return re.sub(r"\D", "", ((p.get("contact") or {}).get("phone") or ""))


def lembretes_pendentes(pendentes, d):
    """{(telefone, início): [agendamentos]} dos lembretes/confirmações de reunião ainda por sair."""
    por = {}
    for p in pendentes:
        slot, tel = slot_do_lembrete(p, d), telefone_de(p)
        if slot and tel:
            por.setdefault((tel, slot), []).append(p)
    return por


def inicio_do_item(item, d):
    h = (item.get("hora_inicio") or "00:00")[:5]
    return datetime.fromisoformat(f"{item['data']}T{h}").replace(tzinfo=d.BRT)


def itens_do_cliente(itens, tel, nome, d):
    """Atendimentos do cliente: telefone na descrição (gravados pelo despachante) ou o mesmo nome (à mão)."""
    alvo = d.sem_acento(nome or "").strip()
    saida = []
    for it in itens:
        tels = RE_TEL.findall(it.get("descricao") or "")
        if tel in tels or tel[2:] in tels:
            saida.append(it)
        elif not tels and len(alvo) >= 3 and d.sem_acento(it.get("nome_cliente") or "").strip() == alvo:
            saida.append(it)
    return saida


def decisao_easyjur(slot, itens, agora, d):
    """Motivo para cancelar pelo que está no EasyJur, ou None (manter / não dá para saber)."""
    no_horario = [i for i in itens if inicio_do_item(i, d) == slot]
    if any(i.get("status") != "S" for i in no_horario):
        return None  # reunião viva naquele horário (a duplicata cancelada não conta)
    if no_horario:
        return "a reunião foi cancelada no EasyJur"
    outras = sorted(inicio_do_item(i, d) for i in itens
                    if i.get("status") in ("A", "N", "P") and inicio_do_item(i, d) > agora)
    if outras:
        return f"a reunião foi remarcada para {d.texto_slot(outras[0])}"
    return None


def pediu_desmarcar(msgs, slot, agora, d):
    """Frase do cliente desmarcando a reunião (depois da última confirmação dela), ou None."""
    marca_dia, marca_hora = f"{slot:%d/%m}", f"{slot:%H}h{slot:%M}"
    confirmacoes = [m for m in msgs if m.get("sender") != "CONTACT" and marca_hora in (m.get("content") or "")
                    and (marca_dia in (m.get("content") or "") or "hoje" in (m.get("content") or ""))]
    if not confirmacoes:
        return None
    desde = d.ler_iso(confirmacoes[-1]["createdAt"])
    limite = min(agora, slot - timedelta(minutes=30))
    for m in msgs:
        quando = d.ler_iso(m["createdAt"])
        if m.get("sender") != "CONTACT" or not (desde < quando <= limite):
            continue
        t = d.sem_acento(m.get("content") or "")
        if RE_DESMARCA.search(t) and not RE_TECNICO.search(t):
            depois = [x for x in msgs if d.ler_iso(x["createdAt"]) > quando and x.get("sender") == "CONTACT"]
            if any(RE_MANTEM.search(d.sem_acento(x.get("content") or "")) for x in depois):
                return None  # mudou de ideia e confirmou
            return (m.get("content") or "").strip()
    return None


def trocar_lembretes(zaia, pendentes, contato_id, inicio, d):
    """Na gravação de uma reunião: cancela os lembretes PENDENTES do mesmo cliente para OUTRO horário (remarcação)
    e diz se já existe lembrete para ESTE horário (aí não agenda de novo). Antes, qualquer mensagem pendente do
    cliente impedia os lembretes da data nova, e os da data antiga continuavam valendo."""
    ja_tem = False
    for p in pendentes:
        if p.get("contactId") != contato_id:
            continue
        slot = slot_do_lembrete(p, d)
        if slot is None:
            continue
        if slot == inicio:
            ja_tem = True
        elif not d.DRY_RUN:
            try:
                zaia.chamar("cancelar_agendamento", agendamentoId=p["id"])
                p["status"] = "CANCELLED"
                _log("lembrete da data antiga cancelado na remarcação")
            except Exception as erro:
                _log(f"cancelamento na remarcação falhou: {type(erro).__name__}")
    return ja_tem


def rodada(zaia, easyjur_fn, conversas, pendentes, agora, contagem, d):
    if _estado["ultima"] and agora - _estado["ultima"] < A_CADA:
        return
    if agora.astimezone(d.BRT).hour not in HORAS:
        return
    _estado["ultima"] = agora
    grupos = lembretes_pendentes([p for p in pendentes if p.get("status", "PENDING") == "PENDING"], d)
    if not grupos:
        return
    hoje = agora.astimezone(d.BRT).date()
    ate = max(s.date() for _, s in grupos) + timedelta(days=30)
    itens, pag = [], 1
    while True:
        r = easyjur_fn().chamar("list_agenda", tipo="ATENDIMENTO", data_interna_inicio=hoje.isoformat(),
                                data_interna_fim=ate.isoformat(), page=pag, page_size=100) or {}
        itens += r.get("data", [])
        if pag >= (r.get("meta") or {}).get("total_pages", 1) or pag >= 3:
            break
        pag += 1
    for (tel, slot), ps in grupos.items():
        if slot <= agora:
            continue
        nome = (ps[0].get("contact") or {}).get("name") or ""
        do_cliente = itens_do_cliente(itens, tel, nome, d)
        if not do_cliente:
            continue  # não achei o atendimento: na dúvida, mantém o lembrete
        motivo = decisao_easyjur(slot, do_cliente, agora, d)
        frase = None
        if not motivo:
            _, msgs = conversas.de(tel)
            frase = pediu_desmarcar(msgs or [], slot, agora, d)
            if frase:
                motivo = "o cliente avisou na conversa que não vai poder"
        if not motivo:
            continue
        contagem["lembretes_cancelados"] = contagem.get("lembretes_cancelados", 0) + len(ps)
        if d.DRY_RUN:
            _log(f"[simulação] cancelaria {len(ps)} lembrete(s) ({motivo.split(' para ')[0]})")
            continue
        feitos = 0
        for p in ps:
            try:
                zaia.chamar("cancelar_agendamento", agendamentoId=p["id"])
                p["status"] = "CANCELLED"
                feitos += 1
            except Exception as erro:
                _log(f"cancelamento falhou: {type(erro).__name__}")
        _log(f"{feitos} lembrete(s) cancelado(s) ({motivo.split(' para ')[0]})")
        chave = (tel, slot)
        if feitos and chave not in _estado["avisados"]:
            _estado["avisados"].add(chave)
            pedido = (f"\nO cliente escreveu: \"{frase[:160]}\"\n👉 Se a reunião não vai mesmo acontecer, marque "
                      "Cancelado no EasyJur. A Annie segue a conversa com ele para remarcar." if frase else "")
            try:
                zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=d.GRUPO, texto=(
                    f"{TITULO} — {nome} ({tel})*\nReunião de {d.texto_slot(slot)}: {motivo}. Cancelei "
                    f"{feitos} mensagem(ns) agendada(s) ao cliente (lembrete ou confirmação), para ele não receber "
                    f"aviso de uma reunião que não vai acontecer.{pedido}"
                    + ("" if frase else "\n_(aviso só para conhecimento)_")))
            except Exception as erro:
                _log(f"aviso ao grupo falhou: {type(erro).__name__}")
