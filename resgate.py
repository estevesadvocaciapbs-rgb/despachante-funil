"""Resgate de reunião que não aconteceu — sem IA (pedido da usuária em 23/10/2026).

Roda dentro do plantão do despachante. Uma vez por hora lista no EasyJur os ATENDIMENTOS de lead
(os que têm o telefone do cliente na descrição) e, para cada cliente, olha a reunião mais recente.
A reunião "não aconteceu POR FALTA DE RETORNO DO CLIENTE" quando, 2 horas depois do início:
- no dia da reunião o cliente recebeu o lembrete/pedido de confirmação e NÃO respondeu nada até 2 horas
  depois do horário (regra da usuária, 23/10: reunião cancelada pelo próprio advogado não entra);
- o atendimento NÃO está Concluído no EasyJur (aberto, ou cancelado por falta de retorno);
- ninguém da equipe falou com o cliente no dia da reunião, e a automação não avisou de cancelamento
  ou remarcação;
- não há reunião nova marcada para esse cliente;
- ninguém da equipe escreveu ao cliente depois do horário e não há contrato/ZapSign na conversa;
- o cliente não está esperando resposta (a última mensagem da conversa não é dele).

Então a Annie manda ao cliente novos horários do mesmo advogado, de tempos em tempos, para o cliente
não se perder: R1 2 horas depois da reunião (no horário comercial), R2 2 dias úteis depois, R3 7 dias,
R4 15 dias e R5 30 dias. Se o cliente responder, a conversa segue o fluxo normal (escolha do horário,
outros horários, gravação no EasyJur); se ele ficar 2 dias úteis em silêncio depois de responder,
o resgate continua de onde parou. Para de vez quando: o atendimento é concluído, há reunião nova,
alguém da equipe escreve ao cliente, aparece contrato, o cliente diz que não quer mais, ou depois do R5.
No R1 o advogado é avisado no privado (📵); 15 dias depois do R5 sem resposta, recebe o aviso final.

Gasto no EasyJur: 1 ou 2 listagens por hora (todas as reuniões de lead, sem filtrar advogado) + a agenda
do advogado só quando vai mandar horários. Privacidade: o log não leva nome nem telefone.
"""

import re
from datetime import date, datetime, timedelta, timezone

COMECO = date(2026, 10, 23)          # só reuniões a partir da entrada no ar (as antigas não são chamadas)
A_CADA = timedelta(minutes=60)
HORAS = range(8, 19)                 # manda ao cliente das 8h às 18h59 (Belém), de segunda a sexta
ESPERA_R1 = timedelta(hours=2)       # depois do início da reunião
CADENCIA_D = [2, 7, 15, 30]          # R2 em dias úteis; R3, R4 e R5 em dias corridos depois da anterior
SILENCIO_UTEIS = 2                   # cliente respondeu e sumiu: retoma depois de 2 dias úteis
AVISO_FINAL_D = 15                   # depois do R5 sem resposta: aviso final ao advogado
JANELA_D = 80
MARCA = "para remarcar a sua conversa"    # está em todas as mensagens de resgate (é o histórico)
AVISO_ADV = "📵 *CLIENTE NÃO VEIO À REUNIÃO"
AVISO_FIM = "📵 *CLIENTE SEM RETORNO"
RE_TEL = re.compile(r"\b55\d{10,11}\b")
# lembretes do dia da reunião (despachante: "Passando para lembrar do seu atendimento de hoje" e
# "Passando para confirmar nosso atendimento de hoje ... Podemos confirmar sua presença?")
RE_LEMBRETE = re.compile(r"(lembrar|confirmar)[^.?!]{0,60}(atendimento|reuniao|conversa)[^.?!]{0,40}\bhoje\b|"
                         r"confirmar sua presenca")
RE_CANCELADA = re.compile(r"\b(cancelad|cancelamos|cancelar|remarcad|remarcar|desmarcad)")
RE_DESISTE = re.compile(
    r"nao (tenho|tem|quero) mais|nao quero (mais|seguir|continuar)|desist|ja resolvi|ja contratei|"
    r"outro advogado|outra advogada|nao preciso mais|pode cancelar|nao me (chame|mande|procure)|"
    r"para de (mandar|me chamar)|pare de (mandar|me chamar)|sem interesse")
_estado = {"ultima": None, "ativos": {}, "avisados": set()}


def _log(msg):
    print(f"[{datetime.now(timezone(timedelta(hours=-3))):%d/%m %H:%M:%S}] resgate: {msg}", flush=True)


def dias_uteis_depois(d, inicio, n):
    """inicio + n dias úteis (segunda a sexta), mantendo a hora."""
    x, contados = inicio, 0
    while contados < n:
        x += timedelta(days=1)
        if x.weekday() < 5:
            contados += 1
    return x


def inicio_da_reuniao(d, item):
    h = (item.get("hora_inicio") or "00:00")[:5]
    return datetime.fromisoformat(f"{item['data']}T{h}").replace(tzinfo=d.BRT)


def resumo_do_atendimento(texto):
    """Tira da descrição o cabeçalho que o despachante grava ("Reunião com lead — ... Link ... . ")."""
    t = re.sub(r"^ATENDIMENTO PRESENCIAL no escritório\.\s*", "", texto or "")
    t = re.sub(r"^Reunião com lead — .*?\(\d+\)\.\s*", "", t)
    t = re.sub(r"^Agendada automaticamente \(.*?\)\.\s*", "", t)
    t = re.sub(r"^Link da videochamada: \S+ \.\s*", "", t)
    return t.strip()


def e_humano(m):
    """Mensagem de alguém da equipe (advogado pelo painel ou pelo comando CLIENTE), não da Annie/automação."""
    return m.get("sender") == "USER" and not (m.get("content") or "").lstrip().startswith("*Annie*")


def texto_resgate(d, n, nome, adv, inicio, dois):
    quem = f"{adv['nome'][0].lower()}{adv['nome'][1:]}"
    pn = d.primeiro_nome(nome)
    lista = "\n".join(d.item_da_oferta(s) for s in dois)
    # a data antiga vai como "23/10 (14h00)": no formato "23/10, às 14h00" ela seria lida como horário ofertado
    quando = f"{inicio:%d/%m} ({inicio:%H}h{inicio:%M})"
    abre = {
        1: f"Oi, {pn}! Senti sua falta na conversa com {quem}, marcada para {quando}. Imprevistos acontecem! "
           f"Se ainda quiser ajuda com o seu caso, estou aqui {MARCA}.",
        2: f"Oi, {pn}! Tudo bem? Passando de novo {MARCA} com {quem}.",
        3: f"Oi, {pn}! Ainda quer ajuda com o seu caso? Estou à disposição {MARCA} com {quem}.",
        4: f"Oi, {pn}! Lembrei de você: se o seu caso ainda precisar de atenção, é só escolher um horário "
           f"{MARCA} com {quem}.",
        5: f"Oi, {pn}! Esta é a minha última mensagem {MARCA} com {quem}.",
    }[n]
    # toda mensagem tem pergunta: sem "?" a retomada automática acharia que a conversa travou
    fecha = {1: "Qual fica melhor pra você? Se preferir outro dia ou horário, é só me dizer.",
             2: "Qual fica melhor pra você?",
             3: "Qual fica melhor pra você? Se preferir outro dia, é só me dizer.",
             4: "Qual fica melhor pra você? Se não quiser mais, é só me avisar que eu não te chamo de novo.",
             5: "Qual fica melhor pra você? Se precisar depois, é só me chamar aqui. 😊"}[n]
    return f"{abre} {d.MARCA_OFERTA}:\n\n{lista}\n\n{fecha}"


def reunioes_por_cliente(d, ej, agora):
    """{telefone: [itens]} dos ATENDIMENTOS com telefone na descrição, dos últimos JANELA_D dias e futuros."""
    hoje = agora.astimezone(d.BRT).date()
    por_tel, pag = {}, 1
    while True:
        r = ej.chamar("list_agenda", tipo="ATENDIMENTO", data_interna_inicio=(hoje - timedelta(days=JANELA_D)).isoformat(),
                      data_interna_fim=(hoje + timedelta(days=90)).isoformat(), page=pag, page_size=100) or {}
        for it in r.get("data", []):
            achado = RE_TEL.search(it.get("descricao") or "")
            if achado:
                por_tel.setdefault(achado.group(0), []).append(it)
        if pag >= (r.get("meta") or {}).get("total_pages", 1) or pag >= 5:
            return por_tel
        pag += 1


def proximo_passo(d, item, msgs, agora):
    """(n, quando) do próximo resgate a mandar, ou (None, motivo) se não é caso de mandar agora/mais."""
    inicio = inicio_da_reuniao(d, item)
    dia = inicio.replace(hour=0, minute=0)
    do_dia = [m for m in msgs if dia <= d.ler_iso(m["createdAt"]) < inicio + ESPERA_R1]
    lembretes = [m for m in do_dia if m.get("sender") != "CONTACT" and d.ler_iso(m["createdAt"]) <= inicio
                 and RE_LEMBRETE.search(d.sem_acento(m.get("content") or ""))]
    if not lembretes:
        return None, "sem lembrete no dia (reunião cancelada antes ou sem pedido de confirmação)"
    if any(m.get("sender") == "CONTACT" for m in do_dia):
        return None, "cliente respondeu no dia da reunião"
    if any(m.get("sender") != "CONTACT" and m not in lembretes and MARCA not in (m.get("content") or "")
           and RE_CANCELADA.search(d.sem_acento(m.get("content") or "")) for m in do_dia):
        return None, "o escritório avisou cancelamento ou remarcação"
    depois = [m for m in msgs if d.ler_iso(m["createdAt"]) >= dia]
    if any(e_humano(m) for m in depois):
        return None, "equipe falou com o cliente"
    if any("zapsign" in d.sem_acento(m.get("content") or "") for m in depois):
        return None, "contrato"
    # o que o cliente escreveu depois da janela da confirmação (antes dela ele não escreveu nada, ver acima)
    cliente = [m for m in depois if m.get("sender") == "CONTACT" and d.ler_iso(m["createdAt"]) >= inicio + ESPERA_R1]
    if any(RE_DESISTE.search(d.sem_acento(m.get("content") or "")) for m in cliente):
        return None, "cliente desistiu"
    if msgs and msgs[-1].get("sender") == "CONTACT":
        return None, "cliente esperando resposta"
    feitos = [m for m in depois if MARCA in (m.get("content") or "")]
    n = len(feitos)
    ult_cliente = max((d.ler_iso(m["createdAt"]) for m in cliente), default=None)
    silencio = dias_uteis_depois(d, ult_cliente, SILENCIO_UTEIS) if ult_cliente else None
    if n == 0:
        quando = silencio if ult_cliente else inicio + ESPERA_R1
    elif n >= 5:
        return None, "fim"
    else:
        ult = d.ler_iso(feitos[-1]["createdAt"])
        base = dias_uteis_depois(d, ult, CADENCIA_D[0]) if n == 1 else ult + timedelta(days=CADENCIA_D[n - 1])
        quando = max(base, silencio) if silencio else base
    return n + 1, quando


def rodada(zaia, easyjur_fn, agenda_fn, conversas, agora, contagem, d, pendentes=(), reservados_fn=None):
    """Devolve os leads em resgate (entram na confirmação do despachante para gravar a nova reunião)."""
    local = agora.astimezone(d.BRT)
    if (_estado["ultima"] and agora - _estado["ultima"] < A_CADA) or (local.hour not in HORAS and _estado["ultima"]):
        return list(_estado["ativos"].values())  # fora do horário só confere uma vez (no começo do plantão)
    _estado["ultima"] = agora
    por_tel = reunioes_por_cliente(d, easyjur_fn(), agora)
    ids_adv = {a["id"]: a for a in d.ADVOGADOS}
    pend = {p.get("contactId") for p in pendentes}
    ativos = {}
    for tel, itens in por_tel.items():
        if tel in d.EQUIPE:
            continue
        item = max(itens, key=lambda i: (i.get("data") or "", i.get("hora_inicio") or ""))
        inicio = inicio_da_reuniao(d, item)
        adv = ids_adv.get(item.get("id_advogado"))
        if (inicio.date() < COMECO or inicio > local or item.get("status") == "C" or not adv
                or local - inicio < ESPERA_R1):
            continue
        conv, msgs = conversas.de(tel)
        if not conv:
            continue
        nome = (conv.get("contact") or {}).get("name") or item.get("nome_cliente") or ""
        n, quando = proximo_passo(d, item, msgs, agora)
        resumo = resumo_do_atendimento(item.get("descricao"))
        lead = {"nome": nome, "tel": tel, "texto": resumo, "quando": inicio, "origem": "resgate"}
        ja_recebeu = any(MARCA in (m.get("content") or "") and d.ler_iso(m["createdAt"]) >= inicio for m in msgs)
        if ja_recebeu and (n is not None or quando in ("fim", "cliente esperando resposta")):
            ativos[tel] = lead  # já recebeu horários: a resposta dele passa pela confirmação do despachante
        if n is None:
            if quando == "fim":
                avisar_fim(zaia, d, conversas, adv, nome, tel, msgs, agora)
            continue
        if quando > agora or local.weekday() >= 5 or local.hour not in HORAS:
            continue
        if conv.get("contact", {}).get("id") in pend:
            continue  # já tem mensagem agendada para ele (lembrete, oferta...)
        reservados = reservados_fn() if reservados_fn else set()
        livres = agenda_fn().livres(adv, reservados)
        if not livres:
            _log("sem horário livre do advogado — resgate fica para a próxima hora")
            continue
        dois = d.manha_e_tarde(livres)
        texto = texto_resgate(d, n, nome, adv, inicio, dois)
        contagem["resgates"] = contagem.get("resgates", 0) + 1
        if d.DRY_RUN:
            _log(f"[simulação] mandaria o resgate R{n}")
            continue
        hora = (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:00.000Z")
        zaia.chamar("agendar_mensagem", contatoId=conv["contact"]["id"], conversaId=conv["id"], mensagem=texto,
                    dataHora=hora, assinatura="ia", ativarIaAoResponder=True)
        ativos[tel] = lead
        _log(f"resgate R{n} agendado ({adv['curto']})")
        if n == 1:
            avisar_advogado(zaia, d, adv, nome, tel, inicio, item)
    _estado["ativos"] = ativos
    return list(ativos.values())


def avisar_advogado(zaia, d, adv, nome, tel, inicio, item):
    situacao = "cancelado no EasyJur" if item.get("status") == "S" else "ainda em aberto no EasyJur"
    try:
        zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"], texto=(
            f"{AVISO_ADV} — {nome} ({tel})*\n"
            f"O cliente não respondeu à confirmação da reunião de {inicio:%d/%m} às {inicio:%H}h{inicio:%M} "
            f"(atendimento {situacao}) e não vi sinal dela (contrato ou mensagem da equipe). "
            "Mandei ao cliente novos horários seus para remarcar "
            "e vou repetir de tempos em tempos (2 dias úteis, 7, 15 e 30 dias) até ele responder.\n"
            "👉 Se a reunião aconteceu, marque Concluído no EasyJur que eu paro. Se for falar você mesmo com o "
            "cliente, é só escrever a ele pelo painel: eu paro também."))
    except Exception as erro:
        _log(f"aviso ao advogado falhou: {type(erro).__name__}")


def avisar_fim(zaia, d, conversas, adv, nome, tel, msgs, agora):
    feitos = [m for m in msgs if MARCA in (m.get("content") or "")]
    if not feitos or tel in _estado["avisados"] or agora - d.ler_iso(feitos[-1]["createdAt"]) < timedelta(days=AVISO_FINAL_D):
        return
    _, privado = conversas.de(adv["tel"])
    if any(AVISO_FIM in (m.get("content") or "") and tel in (m.get("content") or "") for m in privado):
        _estado["avisados"].add(tel)
        return
    if d.DRY_RUN:
        return
    try:
        zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"], texto=(
            f"{AVISO_FIM} — {nome} ({tel})*\n"
            f"Mandei 5 convites para remarcar a reunião (o último em {d.ler_iso(feitos[-1]['createdAt']).astimezone(d.BRT):%d/%m}) "
            "e o cliente não respondeu. Parei de chamar. 👉 Se quiser tentar outra vez, fale com ele pelo painel."))
        _estado["avisados"].add(tel)
    except Exception as erro:
        _log(f"aviso final falhou: {type(erro).__name__}")
