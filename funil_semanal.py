"""Funil da semana (pedido da usuária em 13/11/2026): toda sexta, 17h30, no grupo Firma 2026.

Leads novos que chegaram no WhatsApp (Za.Ia) -> casos triados (oportunidades do EasyJur) -> reuniões agendadas
-> reuniões que estavam marcadas para a semana (realizadas, canceladas, sem baixa) -> contratos fechados.
Também separa por origem, lida do nome da oportunidade no EasyJur ("Tráfego pago", "Indicação ..."), para comparar
com o gerenciador de anúncios. Sem IA; ~8 chamadas ao EasyJur e 3 à Za.Ia por envio.

Repositório PÚBLICO: o log mostra só contagens, nunca nomes ou o texto da mensagem.
"""
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

import despachante
import secretaria

BRT = timezone(timedelta(hours=-3))
GRUPO_FIRMA = "claude-grupo-1"
SEXTA, HORA_ENVIO = 4, (17, 30)
ORIGENS = ("Tráfego pago", "Indicação", "Outros")


def _log(msg):
    print(f"[funil-semanal] {msg}", flush=True)


def _z(zaia, ferramenta, **args):
    """Za.Ia com espera no limite de 60 leituras/minuto (o plantão do despachante divide a mesma cota)."""
    for tentativa in range(6):
        try:
            return zaia.chamar(ferramenta, **args)
        except RuntimeError as e:
            m = re.search(r"aguarde (\d+) segundos", str(e))
            if "Limite de" not in str(e) or tentativa == 5:
                raise
            time.sleep((int(m.group(1)) if m else 20) + 3)


def _todas(ej, ferramenta, paginas=3, **filtro):
    itens, pag = [], 1
    while True:
        r = ej.chamar(ferramenta, page=pag, page_size=100, **filtro) or {}
        itens += r.get("data") or []
        if pag >= min((r.get("meta") or {}).get("total_pages", 1), paginas):
            return itens
        pag += 1


def semana(hoje):
    """Segunda a sexta da semana de `hoje` (no fim de semana, a semana que acabou)."""
    seg = hoje - timedelta(days=hoje.weekday())
    return seg, seg + timedelta(days=4)


def cabecalho(ini, fim):
    return f"📊 *Funil da semana ({ini:%d/%m} a {fim:%d/%m})*"


def origem(nome_oportunidade):
    n = secretaria.norm(nome_oportunidade or "")
    if "trafego" in n or "anuncio" in n:
        return "Tráfego pago"
    if "indicacao" in n or "indicado" in n:
        return "Indicação"
    return "Outros"


def e_reuniao_de_lead(it):
    """ATENDIMENTO marcado com cliente/lead; fora os itens gerados por publicação ou processo e os sem hora."""
    return (not it.get("processo") and not (it.get("codigo_publicacao") or "").strip()
            and (it.get("hora_inicio") or "00:00")[:5] != "00:00")


def _nome(it):
    n = (it.get("nome_cliente") or "").strip()
    if n:
        return n.split()[0].title() if len(n.split()) == 1 else " ".join(n.split()[:2]).title()
    return "sem cliente no EasyJur"


def _nome_dia(it):
    d = it.get("data") or ""
    return f"{_nome(it)} {d[8:10]}/{d[5:7]}" if len(d) >= 10 else _nome(it)


def dados(zaia, ej, ini, fim, agora):
    di, df = ini.isoformat(), fim.isoformat()
    p_ini = datetime(ini.year, ini.month, ini.day, tzinfo=BRT).astimezone(timezone.utc)
    p_fim = (datetime(fim.year, fim.month, fim.day, tzinfo=BRT) + timedelta(days=1)).astimezone(timezone.utc)
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
    rel = _z(zaia, "relatorio_atendimento", periodo={"inicio": iso(p_ini), "fim": iso(p_fim)}) or {}
    contatos = rel.get("contatos") or {}

    criadas = _todas(ej, "list_oportunidades", data_inicio=di, data_fim=df)
    fechadas = _todas(ej, "list_oportunidades", status=["4"], tipo_data="encerramento", data_inicio=di, data_fim=df)
    recusadas = _todas(ej, "list_oportunidades", status=["5"], tipo_data="encerramento", data_inicio=di, data_fim=df)
    marcadas = [i for i in _todas(ej, "list_agenda", tipo="ATENDIMENTO", data_interna_inicio=di, data_interna_fim=df)
                if e_reuniao_de_lead(i)]
    agendadas = [i for i in _todas(ej, "list_agenda", tipo="ATENDIMENTO", data_cadastro_inicio=di, data_cadastro_fim=df)
                 if e_reuniao_de_lead(i)]

    # origem de cada reunião = nome da oportunidade (a de semanas anteriores vem numa leitura só)
    oport = {o["id"]: o for o in criadas + fechadas + recusadas}
    faltam = {i.get("oportunidade") for i in marcadas + agendadas if i.get("oportunidade")} - set(oport)
    if faltam:
        antes = (ini - timedelta(days=60)).isoformat()
        for o in _todas(ej, "list_oportunidades", paginas=2, data_inicio=antes, data_fim=df, sort="-data"):
            oport.setdefault(o["id"], o)
    org = lambda it: origem((oport.get(it.get("oportunidade")) or {}).get("nome"))  # noqa: E731

    hoje, hora = agora.astimezone(BRT).date(), agora.astimezone(BRT).strftime("%H:%M")
    realizadas = [i for i in marcadas if i.get("status") == "C"]
    canceladas = [i for i in marcadas if i.get("status") == "S"]
    vao_acontecer = [i for i in marcadas if i.get("status") not in ("C", "S")
                     and ((i.get("data") or "") > hoje.isoformat()
                          or (i.get("data") == hoje.isoformat() and (i.get("hora_inicio") or "")[:5] > hora))]
    sem_baixa = [i for i in marcadas if i.get("status") not in ("C", "S") and i not in vao_acontecer]

    por_origem = {o: {"triados": 0, "agendadas": 0, "marcadas": 0, "realizadas": 0, "canceladas": 0, "fechados": 0}
                  for o in ORIGENS}
    for o in criadas:
        por_origem[origem(o.get("nome"))]["triados"] += 1
    for o in fechadas:
        por_origem[origem(o.get("nome"))]["fechados"] += 1
    for chave, lista in (("agendadas", agendadas), ("marcadas", marcadas), ("realizadas", realizadas),
                         ("canceladas", canceladas)):
        for i in lista:
            por_origem[org(i)][chave] += 1
    return {"novos": int(contatos.get("novos") or 0), "reengajados": int(contatos.get("reengajados") or 0),
            "triados": criadas, "agendadas": agendadas, "marcadas": marcadas, "realizadas": realizadas,
            "canceladas": canceladas, "sem_baixa": sem_baixa, "vao_acontecer": vao_acontecer,
            "fechados": fechadas, "recusados": recusadas, "por_origem": por_origem}


def _pct(a, b):
    return f"{round(100 * a / b)}%" if b else "sem base"


def _lista(itens, fmt, maximo=8):
    nomes = [fmt(i) for i in itens]
    extra = f" e mais {len(nomes) - maximo}" if len(nomes) > maximo else ""
    return ", ".join(nomes[:maximo]) + extra


def _fechado(o):
    cli = ((o.get("cliente_info") or {}).get("nome") or "").split()
    adv = ((o.get("responsavel_info") or {}).get("nome") or "").split()
    nome = " ".join(cli[:2]).title() if cli else "sem nome"
    return f"{nome} ({origem(o.get('nome')).lower()}{', ' + adv[0].title() if adv else ''})"


def texto(d, ini, fim):
    n_marc, n_real = len(d["marcadas"]), len(d["realizadas"])
    linhas = [cabecalho(ini, fim), "",
              f"👥 *Leads novos no WhatsApp* {d['novos']}",
              f"(mais {d['reengajados']} contatos antigos que voltaram a falar)", "",
              f"📝 *Casos triados* {len(d['triados'])}",
              f"📅 *Reuniões agendadas na semana* {len(d['agendadas'])}", "",
              f"🗓️ *Reuniões marcadas para a semana* {n_marc}",
              f"✅ Realizadas {n_real}"]
    if d["canceladas"]:
        linhas.append(f"❌ Canceladas {len(d['canceladas'])} ({_lista(d['canceladas'], _nome)})")
    else:
        linhas.append("❌ Canceladas 0")
    if d["sem_baixa"]:
        linhas.append(f"❔ Sem baixa no EasyJur {len(d['sem_baixa'])} "
                      f"({_lista(d['sem_baixa'], _nome_dia)})")
    if d["vao_acontecer"]:
        linhas.append(f"⏳ Ainda vão acontecer {len(d['vao_acontecer'])}")
    linhas += ["", f"🤝 *Contratos fechados* {len(d['fechados'])}"]
    if d["fechados"]:
        linhas.append(_lista(d["fechados"], _fechado, maximo=15))
    linhas += [f"🚫 *Não fecharam* {len(d['recusados'])}", "",
               "📈 *Conversão da semana*",
               f"Lead novo para reunião agendada {_pct(len(d['agendadas']), d['novos'])}",
               f"Reunião marcada para realizada {_pct(n_real, n_marc)}",
               f"Reunião realizada para contrato {_pct(len(d['fechados']), n_real)}"]
    t = d["por_origem"]["Tráfego pago"]
    linhas += ["", "🎯 *Só tráfego pago*",
               f"Triados {t['triados']}, reuniões agendadas {t['agendadas']}, marcadas para a semana {t['marcadas']}, "
               f"realizadas {t['realizadas']}, canceladas {t['canceladas']}, contratos {t['fechados']}",
               "", "ℹ️ A origem vem do nome da oportunidade no EasyJur (\"Tráfego pago\", \"Indicação\"). "
               "Oportunidade sem esse nome entra como outros. Reunião sem baixa no EasyJur não dá para saber se "
               "aconteceu, por isso vale concluir ou cancelar no sistema."]
    return "\n".join(linhas)


def ja_enviado(zaia, ini, fim):
    alvo = cabecalho(ini, fim)
    msgs = (_z(zaia, "ler_grupo", grupoId=GRUPO_FIRMA, limit=100) or {}).get("mensagens", [])
    return any(m.get("sender") != "CONTACT" and secretaria.sem_assinatura(m.get("content") or "").startswith(alvo)
               for m in msgs)


def _resumo_log(d):
    return (f"novos {d['novos']}, triados {len(d['triados'])}, agendadas {len(d['agendadas'])}, "
            f"marcadas {len(d['marcadas'])} (realizadas {len(d['realizadas'])}, canceladas {len(d['canceladas'])}, "
            f"sem baixa {len(d['sem_baixa'])}), fechados {len(d['fechados'])}, recusados {len(d['recusados'])}")


def rodada(zaia, ej, agora=None, forcar=False, enviar=True):
    agora = agora or datetime.now(timezone.utc)
    local = agora.astimezone(BRT)
    if not forcar and (local.weekday() != SEXTA or (local.hour, local.minute) < HORA_ENVIO):
        _log("não é sexta depois das 17h30")
        return None
    ini, fim = semana(local.date())
    if ja_enviado(zaia, ini, fim):
        _log("funil desta semana já está no grupo")
        return None
    d = dados(zaia, ej, ini, fim, agora)
    _log(_resumo_log(d))
    msg = texto(d, ini, fim)
    if enviar:
        _z(zaia, "enviar_mensagem_grupo", assinatura="ia", grupoId=GRUPO_FIRMA, texto=msg)
        _log("enviado ao grupo Firma 2026")
    return msg


def main(argv):
    zaia = despachante.MCP(despachante.ZAIA_URL, os.environ.get("ZAIA_TOKEN"), "Za.Ia")
    ej = despachante.MCP(despachante.EASYJUR_URL, os.environ.get("EASYJUR_TOKEN"), "EasyJur")
    simular = "--simular" in argv
    msg = rodada(zaia, ej, forcar="--agora" in argv or simular, enviar=not simular)
    if msg and simular and not os.environ.get("GITHUB_ACTIONS"):  # nomes só na tela local, nunca no log público
        print(msg)
    _log(f"chamadas ao EasyJur: {despachante.ESTADO_EJ['chamadas']}")


if __name__ == "__main__":
    main(sys.argv[1:])
