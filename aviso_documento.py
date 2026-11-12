"""Cliente mandou documento: aviso no privado da advogada responsável, sem IA.

Pedido da usuária (04/11, caso Wellington): em 29/10 o cliente mandou o prontuário da UPA, a Annie respondeu
"vou avisar a equipe" e nada chegou à Dra. Fernanda. Agora, a cada 3 minutos, as conversas com movimento recente
de CLIENTE (etiqueta Cliente ou nome salvo com o nome da advogada) são conferidas: PDF, foto ou vídeo enviados
pelo cliente viram um aviso "📎 DOCUMENTO DE CLIENTE" no privado da advogada. Uma rajada de arquivos vira um aviso
só (espera 4 minutos sem arquivo novo). Advogada: nome salvo ("... Cliente Fernanda"), etiqueta PENDÊNCIA da
advogada, tarefa aberta no nome dela; sem nada disso, a Dra. Danielle. O log não leva nome nem telefone.
"""

from datetime import timedelta

INTERVALO = timedelta(minutes=3)
JANELA = timedelta(minutes=40)
CALMA = timedelta(minutes=4)     # espera a rajada de arquivos terminar
MARCA = "📎 *DOCUMENTO DE CLIENTE"
TIPOS = {"DOCUMENT": "PDF/arquivo", "IMAGE": "Foto", "VIDEO": "Vídeo"}
MAX_ITENS = 8
_estado = {"ultima": None}
_vistos = {}    # conversa -> lastMessageAt já conferido
_avisado = {}   # conversa -> createdAt do último arquivo já avisado


def advogado(contato, tarefas, d):
    """Advogado do cliente, ou None se o contato não é cliente."""
    nome = d.sem_acento((contato.get("name") or "").strip()).split()
    etiquetas = {d.sem_acento(e.get("name") or "") for e in contato.get("labels") or []}
    cliente = "cliente" in etiquetas
    # "... Cliente Fernanda" é como a equipe salva os clientes dela; Lucas/Danielle no fim do nome só valem se o
    # contato já é cliente (um lead "Pedro Lucas" não é cliente do Dr. Lucas)
    por_nome = {"fernanda": d.FERNANDA, "lucas": d.LUCAS, "danielle": d.DANIELLE, "dani": d.DANIELLE}
    if len(nome) >= 2 and nome[-1] in por_nome and nome[0] not in ("dra.", "dra", "dr.", "dr") and (
            cliente or nome[-1] == "fernanda"):
        return por_nome[nome[-1]]
    for adv, et in ((d.FERNANDA, "pendencia fernanda"), (d.DANIELLE, "pendencia dani"), (d.LUCAS, "pendencia lucas")):
        if et in etiquetas:
            return adv
    membros = {"claude-usuario-3": d.FERNANDA, "claude-usuario-1": d.DANIELLE, "claude-usuario-2": d.LUCAS}
    import tarefas_limpas
    for t in tarefas:  # tarefa de briefing de lead não conta: lead em triagem manda foto o tempo todo
        if (t.get("contatoId") == contato.get("id") and not t.get("completedAt") and t.get("assigneeId") in membros
                and not tarefas_limpas.e_briefing(t)):
            return membros[t["assigneeId"]]
    return d.DANIELLE if cliente else None


def arquivos_novos(msgs, conv_id, agora, d):
    """Arquivos do cliente ainda não avisados; vazio enquanto a rajada não terminou."""
    novos = [m for m in msgs if m.get("sender") == "CONTACT" and m.get("contentType") in TIPOS
             and timedelta(0) <= agora - d.ler_iso(m["createdAt"]) <= JANELA and m["createdAt"] > _avisado.get(conv_id, "")]
    if not novos or agora - d.ler_iso(novos[-1]["createdAt"]) < CALMA:
        return []
    return novos


def texto_aviso(nome, tel, novos, d):
    hora = lambda m: d.ler_iso(m["createdAt"]).astimezone(d.BRT).strftime("%d/%m %H:%M")
    itens = [f"• {TIPOS[m['contentType']]}: {(m.get('content') or '').strip()[:90] or '(sem descrição)'}"
             for m in novos[:MAX_ITENS]]
    if len(novos) > MAX_ITENS:
        itens.append(f"• e mais {len(novos) - MAX_ITENS}")
    quando = hora(novos[0]) if len(novos) == 1 else f"{hora(novos[0])} a {hora(novos[-1])[-5:]}"
    return (f"{MARCA} — {nome} ({tel})*\n"
            + ("Chegou 1 arquivo" if len(novos) == 1 else f"Chegaram {len(novos)} arquivos")
            + f" pelo WhatsApp em {quando}:\n" + "\n".join(itens) +
            f"\n(último às {hora(novos[-1])})\n👉 Os arquivos estão na conversa do cliente na Za.Ia.")


def privado(zaia, adv):
    conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=adv["tel"]) or {}).get("conversa")
    return (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []) if conv else []


def ja_avisado(msgs, tel, ultimo):
    """Outro plantão já mandou este aviso? (o estado em memória some quando o plantão reinicia)"""
    marca = f"(último às {ultimo})"
    return any(MARCA in (m.get("content") or "") and tel in (m.get("content") or "") and marca in (m.get("content") or "")
               for m in msgs)


def rodada(zaia, agora, contagem, d, tarefas):
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    lista = zaia.chamar("listar_conversas", limit=100, periodo={
        "inicio": (agora - JANELA).astimezone(d.timezone.utc).strftime(fmt),
        "fim": agora.astimezone(d.timezone.utc).strftime(fmt)}) or {}
    advogados = {a["tel"] for a in d.ADVOGADOS}
    for at in lista.get("atendimentos", []):
        conv = at.get("conversa") or {}
        tel = (at.get("phone") or "").strip()
        if (not conv.get("id") or not tel or tel in d.EQUIPE or tel in advogados
                or conv.get("status") not in ("OPEN", "ASSIGNED")):
            continue
        chave = (at.get("lastMessageAt"), _avisado.get(conv["id"]))
        if _vistos.get(conv["id"]) == chave:
            continue
        contatos = (zaia.chamar("buscar_contatos", query=tel, limit=5) or {}).get("contatos", [])
        contato = next((c for c in contatos if c.get("phone") == tel), None)
        adv = advogado(contato, tarefas, d) if contato else None
        if not adv:
            _vistos[conv["id"]] = chave
            continue
        msgs = sorted((zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []),
                      key=lambda m: m["createdAt"])
        novos = arquivos_novos(msgs, conv["id"], agora, d)
        if not novos:
            if not any(m.get("sender") == "CONTACT" and m.get("contentType") in TIPOS
                       and m["createdAt"] > _avisado.get(conv["id"], "") and agora - d.ler_iso(m["createdAt"]) < CALMA
                       for m in msgs):
                _vistos[conv["id"]] = chave  # sem rajada em andamento: só relê quando a conversa mexer
            continue
        nome = (contato.get("name") or at.get("name") or "Cliente").strip()
        texto = texto_aviso(nome, tel, novos, d)
        ultimo = d.ler_iso(novos[-1]["createdAt"]).astimezone(d.BRT).strftime("%d/%m %H:%M")
        _avisado[conv["id"]] = novos[-1]["createdAt"]
        _vistos[conv["id"]] = (at.get("lastMessageAt"), _avisado[conv["id"]])
        if d.DRY_RUN:
            d.log("[simulação] avisaria documento de cliente à advogada")
            continue
        msgs_adv = privado(zaia, adv)
        if ja_avisado(msgs_adv, tel, ultimo):
            continue
        try:  # o que vai acontecer com os arquivos no Drive, com código D para o advogado decidir (12/11)
            import pasta_cliente
            bloco = pasta_cliente.bloco_aviso(pasta_cliente.proximo_codigo(msgs_adv), nome, contato, msgs, tarefas,
                                              adv, agora, d)
            if bloco:
                texto += "\n\n" + bloco
        except Exception as erro:
            d.log(f"pasta do cliente não consultada: {type(erro).__name__}")
        zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"], texto=texto)
        contagem["documentos_avisados"] = contagem.get("documentos_avisados", 0) + 1
        d.log(f"documento de cliente avisado ({adv['curto']})")
