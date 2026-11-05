"""Faxina das conversas já resolvidas — sem IA (pedido da usuária em 05/11/2026).

A equipe costuma pôr a etiqueta "Finalizado" no contato e deixar a conversa aberta; a etiqueta de pendência
do advogado também fica para trás. Com isso os relatórios de pendências traziam assunto já resolvido.
Quatro vezes por dia (9h, 12h, 15h e 17h, antes do relatório das 17h30) esta faxina:

1. olha os contatos com etiqueta de pendência (Dani, Fernanda, Lucas, Thalyta) e as conversas abertas
   dos últimos 3 dias de contatos com "Finalizado" ou "CANCELADO";
2. considera RESOLVIDA a conversa parada há pelo menos 2 horas em que
   - o contato tem "Finalizado"/"CANCELADO" e o cliente não mandou pedido novo depois da última resposta
     do escritório, ou
   - a última palavra do cliente só encerra o assunto ("obrigada", "ok", "certo", emoji...) e, se o
     escritório respondeu depois, não fez pergunta nenhuma.
   Mensagem só da Annie não conta como resposta do escritório (pergunta respondida só pela IA fica aberta);
3. na conversa resolvida: encerra a conversa na Za.Ia (não manda nada ao cliente) e tira as etiquetas de
   pendência do contato. Conversa já encerrada pela equipe também perde a etiqueta de pendência.

Nunca mexe em: grupo, telefone da equipe, contato com mensagem agendada (lembrete de reunião, resgate) ou
com tarefa aberta no kanban, e conversa em que o cliente mandou pergunta, pedido ou arquivo sem resposta.
O log não leva nome nem telefone.
"""

import re
from datetime import timedelta

HORAS = (9, 12, 15, 17)
PENDENCIAS = {"claude-etiqueta-6": "PENDÊNCIA DANI", "claude-etiqueta-12": "PENDÊNCIA FERNANDA",
              "claude-etiqueta-13": "PENDÊNCIA LUCAS", "claude-etiqueta-16": "PENDÊNCIA THALYTA"}
FINAIS = {"claude-etiqueta-5", "claude-etiqueta-11"}  # Finalizado, CANCELADO
PARADA = timedelta(hours=2)
JANELA_ABERTAS = timedelta(days=3)
MAX_CONTATOS = 120  # por faxina (cada um custa uma busca e uma leitura de conversa na Za.Ia)
# só encerra o assunto (texto sem acento, minúsculo, sem pontuação no fim)
RE_FECHO = re.compile(
    r"^(e )?(ok+|okay|ta|ta bom|ta certo|ta otimo|certo|certinho|beleza|blz|show|perfeito|otimo|combinado|"
    r"entendi|entendido|ah sim|sim sim|de nada|por nada|amem|gracas a deus|tudo bem|tudo certo|"
    r"valeu|vlw|obrigad[oa]s?|muito obrigad[oa]s?|obg|brigad[oa]|grat[oa]|gratidao|agradeco|"
    r"ja resolvi|resolvido|ja deu certo|deu certo|nao preciso mais|ate mais|ate logo|tchau|"
    r"deus abencoe|fica com deus|igualmente|amem)"  # "bom dia" sozinho costuma abrir pedido novo: não encerra
    r"([ ,!.]+(ok|obrigad[oa]s?|doutora?|dra|dr|pela atencao|por tudo|viu|tudo|sim|bom dia|boa tarde|"
    r"boa noite|deus abencoe|igualmente|valeu|muito|mesmo|amem|ate mais|abracos?))*[ !.]*$")
RE_SO_EMOJI = re.compile(r"^[\W_]+$")
_estado = {"hora": None}


def encerra_assunto(texto, d):
    t = d.sem_acento(texto or "").strip()
    if not t or "?" in t or len(t) > 70:
        return False
    return bool(RE_SO_EMOJI.match(t) or RE_FECHO.match(t))


def resolvida(msgs, labels, agora, d):
    """msgs em ordem crescente. True se a conversa pode ser encerrada."""
    if not msgs:
        return False
    if agora - d.ler_iso(msgs[-1]["createdAt"]) < PARADA:
        return False  # conversa ainda em andamento
    # resposta só da Annie (IA) não resolve nada: decide pelo que o cliente e as PESSOAS do escritório disseram
    msgs = [m for m in msgs if m.get("sender") == "CONTACT" or not (m.get("content") or "").lstrip().startswith("*Annie*")]
    if not msgs:
        return False
    do_cliente_final = []
    for m in reversed(msgs):  # mensagens do cliente depois da última resposta do escritório
        if m.get("sender") != "CONTACT":
            break
        do_cliente_final.append(m)
    if do_cliente_final:
        # cliente falou por último: só sai se TODAS as últimas falas dele só encerram o assunto
        return all((m.get("content") or "").strip() and encerra_assunto(m.get("content"), d)
                   for m in do_cliente_final)
    # escritório falou por último
    if labels & FINAIS:
        return True
    ultima_cli = next((m for m in reversed(msgs) if m.get("sender") == "CONTACT"), None)
    depois = [m for m in msgs if ultima_cli and m["createdAt"] > ultima_cli["createdAt"]]
    return bool(ultima_cli and encerra_assunto(ultima_cli.get("content"), d)
                and not any("?" in (m.get("content") or "") for m in depois))


def candidatos(zaia, agora):
    """{contato_id: contato} com etiqueta de pendência + abertas recentes de quem tem Finalizado/CANCELADO."""
    cont = {}
    for nome in PENDENCIAS.values():
        off = 0
        while True:
            r = zaia.chamar("listar_contatos", etiqueta=nome, limit=100, offset=off) or {}
            for c in r.get("contatos", []):
                cont[c["id"]] = c
            off += 100
            if off >= (r.get("total") or 0):
                break
    ini = (agora - JANELA_ABERTAS).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    fim = agora.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    for status in ("OPEN", "ASSIGNED"):
        r = zaia.chamar("listar_conversas", status=status, limit=100, periodo={"inicio": ini, "fim": fim}) or {}
        for conv in r.get("conversas", []):
            c = conv.get("contact") or {}
            if c.get("id") and c["id"] not in cont and c.get("phone"):
                cont[c["id"]] = dict(c, labels=None)  # etiquetas vêm depois, pela busca
    return cont


def rodada(zaia, agora, contagem, d, pendentes=(), tarefas=()):
    local = agora.astimezone(d.BRT)
    if local.hour not in HORAS or local.weekday() > 5 or _estado["hora"] == (local.date(), local.hour):
        return
    _estado["hora"] = (local.date(), local.hour)
    agendados = {p.get("contactId") for p in pendentes}
    com_tarefa = {t.get("contatoId") for t in tarefas if not t.get("completedAt")}
    encerradas = etiquetas = vistos = 0
    for cid, c in list(candidatos(zaia, agora).items())[:MAX_CONTATOS]:
        tel = re.sub(r"\D", "", c.get("phone") or "")
        if not tel or len(tel) > 13 or tel.startswith("120363") or tel in d.EQUIPE:
            continue
        if cid in agendados or cid in com_tarefa:
            continue
        if c.get("labels") is None:
            achados = (zaia.chamar("buscar_contatos", query=tel, limit=5) or {}).get("contatos", [])
            c = next((x for x in achados if x.get("id") == cid), None)
            if not c:
                continue
        labels = {l.get("id") for l in c.get("labels") or []}
        pend = labels & set(PENDENCIAS)
        if not pend and not labels & FINAIS:
            continue
        vistos += 1
        conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=tel) or {}).get("conversa")
        if not conv:
            continue
        fechada = conv.get("status") == "CLOSED"
        if not fechada:
            msgs = sorted((zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []),
                          key=lambda m: m["createdAt"])
            if not resolvida(msgs, labels, agora, d):
                continue
        if d.DRY_RUN:
            d.log(f"[simulação] faxina: encerraria a conversa e tiraria {len(pend)} etiqueta(s) de pendência")
            continue
        if not fechada:
            zaia.chamar("encerrar_conversa", conversaId=conv["id"],
                        motivo="Assunto resolvido (faxina automática: Finalizado ou cliente encerrou)")
            encerradas += 1
        for et in pend:
            zaia.chamar("remover_etiqueta_contato", contatoId=cid, etiquetaId=et)
            etiquetas += 1
    contagem["faxina"] = encerradas
    d.log(f"faxina: {vistos} contato(s) conferido(s), {encerradas} conversa(s) encerrada(s), "
          f"{etiquetas} etiqueta(s) de pendência retirada(s)")
