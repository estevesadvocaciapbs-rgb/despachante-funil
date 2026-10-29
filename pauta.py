"""Pauta da reunião semanal de sexta (pedido da usuária, 29/10/2026), sem IA.

Quinta a partir das 17h (Belém): cria no EasyJur a REUNIÃO de sexta às 10h e pede a pauta aos três advogados no
privado. Até sexta 12h: cada resposta que começa com PAUTA (ou HORÁRIO) entra na descrição da reunião e recebe um ✅.
Sexta às 8h: manda a pauta consolidada aos três. Mudança de horário fica no EasyJur (a sugestão só é anotada).
Usa as conversas que a secretaria já baixou na rodada: nenhuma leitura a mais na Za.Ia.
A própria reunião no EasyJur guarda o estado (pedido enviado, pauta enviada): reiniciar o plantão não repete nada.
"""

import re
from datetime import datetime, time, timedelta

import secretaria as s

TITULO = "Reunião semanal da equipe"
PEDIDO = "🗓️ *Pauta da reunião de sexta, {}*"
ENVIADA = "(Pauta enviada aos advogados no WhatsApp às 8h.)"
ADVS = s.ADVOGADAS_RESUMO + [s.DR_LUCAS]
DANI, LUCAS = 344269, 344268
RE_PAUTA = re.compile(r"^\s*\*?pauta\*?(?=\W|$)[\s:\-–]*", re.I)
RE_HORA = re.compile(r"^\s*\*?hor[aá]rio\*?[\s:\-–]+(.+)$", re.I)
RE_ITEM = re.compile(r"^\s*(?:[-•*·]|\d+[.)])\s*")
_estado = {}  # criada / resumo: a sexta já tratada neste plantão (evita consultar o EasyJur a cada minuto)


def sexta_da_semana(agora_brt):
    """A sexta da reunião enquanto a janela está aberta (quinta 17h até sexta 12h); senão None."""
    d, h = agora_brt.date(), agora_brt.time()
    if d.weekday() == 3 and h >= time(17):
        return d + timedelta(days=1)
    if d.weekday() == 4 and h < time(12):
        return d
    return None


def hora_de_pedir(agora_brt):
    """Pedido só em horário comercial: quinta 17h–20h; se perdeu (plantão parado), sexta 7h–9h30."""
    d, h = agora_brt.date(), agora_brt.time()
    return (d.weekday() == 3 and time(17) <= h < time(20)) or (d.weekday() == 4 and time(7) <= h < time(9, 30))


def texto_pedido(adv, sexta, hoje=False):
    return (PEDIDO.format(s.ddmm(sexta)) + "\n"
            f"{adv['nome']}, quais assuntos você quer levar à reunião de {'hoje' if hoje else 'amanhã'}? "
            "Caso que precisa da opinião de "
            "todos, algo para conferir em conjunto, aviso para a equipe...\n"
            "Responda aqui começando com *PAUTA*, um assunto por linha. Exemplo:\n"
            "PAUTA\n- Conferir o cálculo do caso Fulano\n- Escala de atendimentos de novembro\n"
            "Se preferir outro horário, acrescente uma linha *HORÁRIO 9h30*. Sem isso, fica às 10h.\n"
            "Nada a tratar? Responda *PAUTA nada*.")


def ler_resposta(texto):
    """(itens, horario) de uma resposta PAUTA/HORÁRIO; None se a mensagem não é resposta de pauta."""
    linhas = [l for l in s.sem_assinatura(texto or "").splitlines() if l.strip()]
    if not linhas or not (RE_PAUTA.match(linhas[0]) or RE_HORA.match(linhas[0])):
        return None
    itens, horario = [], None
    for i, l in enumerate(linhas):
        h = RE_HORA.match(l)
        if h:
            horario = h.group(1).strip()
            continue
        if i == 0:
            l = RE_PAUTA.sub("", l, count=1)
        l = RE_ITEM.sub("", l).strip()
        if l and s.norm(l) not in ("nada", "nenhuma", "nenhum", "sem pauta"):
            itens.append(l)
    return itens, horario


def bloco(adv, itens, horario):
    linhas = [f"{adv['nome']}:"] + [f"- {i}" for i in itens] if itens else [f"{adv['nome']}: nada a tratar"]
    if horario:
        linhas.append(f"⏰ {adv['nome']} sugere {horario}")
    return "\n".join(linhas)


def descricao_inicial(sexta):
    return (f"{TITULO} — sexta {s.ddmm(sexta)}, 10h (horário padrão; se combinarem outro, mude aqui no EasyJur).\n"
            "Participantes: Dra. Danielle, Dra. Fernanda e Dr. Lucas.\n\n"
            "PAUTA (atualizada sozinha com as respostas PAUTA do WhatsApp até sexta 12h):")


def reuniao(ej, sexta):
    itens = (ej.chamar("list_agenda", id_responsavel_qualquer=DANI, data_interna_inicio=sexta.isoformat(),
                       data_interna_fim=sexta.isoformat(), page_size=100) or {}).get("data") or []
    return next((i for i in itens if (i.get("descricao") or "").startswith(TITULO) and i.get("status") != "S"), None)


def rodada(zaia, ej_fn, lidas, agora, log=print):
    agora_brt = agora.astimezone(s.BRT)
    sexta = sexta_da_semana(agora_brt)
    if not sexta:
        return
    novas = []  # (adv, mensagem, itens, horario) ainda sem ✅
    for adv in ADVS:
        msgs = lidas.get(adv["tel"]) or []
        ja = "\n".join(m.get("content") or "" for m in msgs if m.get("sender") != "CONTACT")
        inicio = datetime.combine(sexta - timedelta(days=1), time(17), s.BRT)
        for m in msgs:
            if m.get("sender") != "CONTACT" or s.ler_iso(m["createdAt"]) < inicio or s.marca(m) in ja:
                continue
            r = ler_resposta(m.get("content"))
            if r:
                novas.append((adv, m) + r)
    hora_resumo = agora_brt.date() == sexta and agora_brt.time() >= time(8) and _estado.get("resumo") != sexta
    criar = hora_de_pedir(agora_brt) and _estado.get("criada") != sexta
    if not novas and not criar and not hora_resumo:
        return  # nada a fazer: não gasta chamada do EasyJur
    ej = ej_fn()
    item = reuniao(ej, sexta)
    if not item and criar:
        r = ej.chamar("create_agenda", tipo="REUNIAO", id_advogado=DANI, id_advogado2=LUCAS, data=sexta.isoformat(),
                      data_fim=sexta.isoformat(), hora_inicio="10:00", hora_fim="11:00", local="Escritório",
                      descricao=descricao_inicial(sexta)) or {}
        novo = (r.get("data") or {}).get("id")
        log(f"pauta: reunião de {s.ddmm(sexta)} criada no EasyJur ({novo})")
        for adv in ADVS:
            try:
                zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"],
                            texto=texto_pedido(adv, sexta, hoje=agora_brt.date() == sexta))
            except Exception as erro:
                log(f"pauta: pedido a {adv['chave']} falhou: {type(erro).__name__}")
        item = reuniao(ej, sexta)
    if not item:
        return
    _estado["criada"] = sexta
    desc = item.get("descricao") or ""
    for adv, m, itens, horario in novas:
        b = bloco(adv, itens, horario)
        if b not in desc:
            desc = desc.rstrip() + "\n\n" + b
            ej.chamar("update_agenda", agenda_id=item["id"], descricao=desc)
        zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"],
                    texto=f"🗓️ ✅ Pauta anotada na reunião de sexta, {s.ddmm(sexta)}, no EasyJur. "
                          f"Pode mandar mais com outro *PAUTA*.\n_{s.marca(m)}_")
    if hora_resumo and ENVIADA not in desc:
        pauta = desc.split("\n\n", 2)[-1] if desc.count("\n\n") >= 2 else "Nenhum assunto enviado."
        hora = str(item.get("hora_inicio") or "10:00")[:5].replace(":00", "h").replace(":", "h")
        for adv in ADVS:
            zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"],
                        texto=f"🗓️ *Pauta da reunião de hoje, {s.ddmm(sexta)}, {hora}*\n{pauta}\n"
                              "_Horário e pauta também estão na agenda do EasyJur._")
        ej.chamar("update_agenda", agenda_id=item["id"], descricao=desc.rstrip() + "\n\n" + ENVIADA)
    if hora_resumo:
        _estado["resumo"] = sexta
