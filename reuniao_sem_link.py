"""Reunião online gravada à mão no EasyJur, sem link — caso Janilza, 27/10/2026.

A equipe remarcou a reunião direto no EasyJur (local "Online", sem Meet). Como não passou pelo despachante,
ninguém criou o evento no Google Agenda nem mandou o link ao cliente. Esta rodada, a cada 30 minutos, olha os
ATENDIMENTOS dos próximos 3 dias com local sem link (e que não são presenciais) e:

  1. cria o evento com Meet na agenda do escritório (pela ponte do Google Agenda);
  2. grava o link no campo local do EasyJur (é o que marca a reunião como resolvida);
  3. manda o link ao cliente (das 7h às 21h) e agenda os lembretes de sempre (8h do dia e 1 hora antes);
  4. avisa o advogado no privado.

Se o link já foi mandado na conversa, só copia esse link para o EasyJur. Sem telefone do cliente (nem na
descrição, nem no cadastro do EasyJur, nem um contato único com o nome na Za.Ia): avisa a equipe no grupo uma vez.
Gasto no EasyJur: 1 listagem a cada 30 minutos + 1–2 chamadas por reunião corrigida.
"""

import re
from datetime import datetime, timedelta, timezone

A_CADA = timedelta(minutes=30)
DIAS = 3
HORAS_CLIENTE = range(7, 21)      # mensagem ao cliente só das 7h às 20h59 (Belém)
FOLGA = timedelta(minutes=20)     # reunião que começa em menos de 20 min: não mexe (a equipe resolve)
RE_TEL = re.compile(r"\((55\d{10,11})\)")
RE_MEET = re.compile(r"https://meet\.google\.com/[a-z0-9-]+")
TITULO = "🔗 *LINK DA REUNIÃO ENVIADO*"
SEM_TEL = "📵 *REUNIÃO ONLINE SEM LINK E SEM TELEFONE*"
_estado = {"ultima": None, "avisados": set()}


def _log(msg):
    print(f"[{datetime.now(timezone(timedelta(hours=-3))):%d/%m %H:%M:%S}] sem link: {msg}", flush=True)


def precisa_link(item, d, agora):
    """Início da reunião (datetime em Belém) se for atendimento online futuro sem link; senão None."""
    if item.get("tipo") != "ATENDIMENTO" or item.get("status") not in ("A", "N"):
        return None
    local = d.sem_acento(item.get("local") or "")
    desc = d.sem_acento(item.get("descricao") or "")
    if "http" in local or "meet.google" in desc or "presencial" in local + desc or "escritorio" in local:
        return None
    if (item.get("hora_inicio") or "00:00") == "00:00":
        return None
    inicio = datetime.strptime(f"{item['data']} {item['hora_inicio']}", "%Y-%m-%d %H:%M").replace(tzinfo=d.BRT)
    if inicio - agora < FOLGA or inicio - agora > timedelta(days=DIAS):
        return None
    return inicio


def advogado_do_item(item, d):
    por_id = {a["id"]: a for a in d.ADVOGADOS}
    return por_id.get(item.get("id_advogado")) or por_id.get(item.get("id_advogado2"))


def telefone(item, zaia, ej, d):
    achado = RE_TEL.search(item.get("descricao") or "")
    if achado:
        return achado.group(1)
    if item.get("cliente"):
        p = (ej.chamar("get_pessoa", pessoa_id=item["cliente"]) or {}).get("data") or {}
        for campo in ("celular", "celular2", "telefone", "telefone2"):
            dig = re.sub(r"\D", "", str(p.get(campo) or ""))
            if len(dig) in (10, 11):
                return "55" + dig
            if len(dig) in (12, 13) and dig.startswith("55"):
                return dig
    nome = (item.get("nome_cliente") or "").strip()
    if len(nome) >= 3:
        cs = (zaia.chamar("buscar_contatos", query=nome, limit=10) or {}).get("contatos", [])
        cs = [c for c in cs if c.get("phone") and d.sem_acento(c.get("name") or "").strip() == d.sem_acento(nome)]
        if len(cs) == 1:
            return cs[0]["phone"]
    return None


def rodada(zaia, easyjur_fn, conversas, agora, contagem, d, pendentes=()):
    if _estado["ultima"] and agora - _estado["ultima"] < A_CADA:
        return
    _estado["ultima"] = agora
    local = agora.astimezone(d.BRT)
    hoje = local.date()
    ej = easyjur_fn()
    itens = (ej.chamar("list_agenda", tipo="ATENDIMENTO", data_interna_inicio=hoje.isoformat(),
                       data_interna_fim=(hoje + timedelta(days=DIAS)).isoformat(), page_size=100) or {}).get("data", [])
    for item in itens:
        inicio = precisa_link(item, d, local)
        adv = advogado_do_item(item, d)
        if not inicio or not adv:
            continue
        nome = (item.get("nome_cliente") or "").strip()
        tel = telefone(item, zaia, ej, d)
        if not tel:
            avisar_sem_telefone(zaia, d, item, adv, inicio)
            continue
        conv, msgs = conversas.de(tel)
        if not conv:
            avisar_sem_telefone(zaia, d, item, adv, inicio)
            continue
        nome = nome or (conv.get("contact") or {}).get("name") or ""
        cadastro = datetime.strptime(item.get("data_cadastro") or item["data"], "%Y-%m-%d").replace(tzinfo=d.BRT)
        ja_mandado = [l for m in msgs if m.get("sender") != "CONTACT" and d.ler_iso(m["createdAt"]) >= cadastro
                      for l in RE_MEET.findall(m.get("content") or "")]
        contagem["sem_link"] = contagem.get("sem_link", 0) + 1
        if d.DRY_RUN:
            _log("[simulação] reunião online sem link — criaria o Meet e mandaria ao cliente")
            continue
        if ja_mandado:  # a equipe já mandou um link: só registra no EasyJur
            ej.chamar("update_agenda", agenda_id=item["id"], local=ja_mandado[-1])
            _log("link já enviado na conversa — copiado para o EasyJur")
            continue
        import agenda_google
        fim = inicio + timedelta(minutes=d.DURACAO_MIN)
        google = agenda_google.criar_reuniao(
            f"Reunião {adv['curto'].replace(' Esteves', '').replace(' Mesquita', '')} — {nome}", nome, inicio, fim,
            f"Lead: {nome} ({tel}). Reunião gravada à mão no EasyJur (nº {item['id']}); link criado pelo despachante.",
            d.email_do_advogado(zaia, adv))
        link = (google or {}).get("link") or ""
        if not link:
            _log("Google Agenda não devolveu link — tenta na próxima rodada")
            continue
        ej.chamar("update_agenda", agenda_id=item["id"], local=link)
        contato_id, conv_id = conv["contact"]["id"], conv["id"]
        quem = f"{adv['nome'][0].lower()}{adv['nome'][1:]}"
        if local.hour in HORAS_CLIENTE:
            quando = (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:00.000Z")
        else:  # de noite: o link vai às 7h (ou 30 min antes, se a reunião for cedo)
            sete = local.replace(hour=7, minute=0, second=0, microsecond=0)
            sete = sete if sete > local else sete + timedelta(days=1)
            quando = min(sete, inicio - timedelta(minutes=30)).astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:00.000Z")
        zaia.chamar("agendar_mensagem", contatoId=contato_id, conversaId=conv_id, dataHora=quando,
                    assinatura="ia", ativarIaAoResponder=True, mensagem=(
                        f"Olá, {d.primeiro_nome(nome)}! Este é o link do seu atendimento com {quem}, "
                        f"{d.texto_slot(inicio)}, por videochamada: {link} — é só clicar nele na hora marcada. "
                        "Eu te mando lembrete antes. Até lá!"))
        tem_pendente = any(p.get("contactId") == contato_id for p in pendentes)
        agendados = [] if tem_pendente else d.lembretes(zaia, contato_id, conv_id, nome, adv, inicio, local, link)
        try:
            zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"], texto=(
                f"{TITULO} — {nome} ({tel})\n"
                f"{d.texto_slot(inicio)} · Online · a reunião foi gravada à mão no EasyJur sem link; criei o evento "
                f"no Google Agenda e mandei o link ao cliente.\n🔗 Link: {link}\n"
                f"Lembretes: {', '.join(agendados) if agendados else 'já havia mensagem agendada'}"))
        except Exception as erro:
            _log(f"aviso ao advogado falhou: {type(erro).__name__}")
        _log("reunião sem link: Meet criado, EasyJur atualizado e link agendado ao cliente")


def avisar_sem_telefone(zaia, d, item, adv, inicio):
    marca = f"#A{item['id']}"
    if marca in _estado["avisados"]:
        return
    _estado["avisados"].add(marca)
    grupo = (zaia.chamar("ler_grupo", grupoId=d.GRUPO, limit=80) or {}).get("mensagens", [])
    if any(marca in (m.get("content") or "") for m in grupo):
        return  # já avisado (os plantões recomeçam a cada 6 horas)
    if d.DRY_RUN:
        return
    zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=d.GRUPO, texto=(
        f"{SEM_TEL}\n{(item.get('nome_cliente') or (item.get('descricao') or '')[:60]).strip()} · {adv['curto']} · "
        f"{d.texto_slot(inicio)}\nNão achei o WhatsApp do cliente para mandar o link. 👉 Vincule o cliente (com "
        f"celular) a esse atendimento no EasyJur, ou ponha o telefone na descrição, que eu crio o Meet e mando o "
        f"link. _(EasyJur nº {item['id']})_ {marca}"))
