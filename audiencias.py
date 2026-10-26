"""Audiência designada em publicação → agenda do EasyJur + alerta ao advogado — sem IA (pedido da usuária, 26/10/2026).

Roda dentro do plantão do despachante, a cada 2 horas, das 7h às 19h (Belém). Lê no EasyJur as publicações dos
últimos 3 dias da Dra. Danielle e da Dra. Fernanda (termos monitorados) e procura no texto a DESIGNAÇÃO de
audiência (designo/redesigno/fica designada/inclua-se em pauta... + data + hora). Quando acha UMA data e hora
futuras sem dúvida:
- cadastra a AUDIENCIA na agenda do EasyJur do advogado, no dia e hora da publicação, ligada ao processo e à
  publicação, com o link da sala do TRIBUNAL (Zoom/Teams/etc.) no local — nunca Google Meet;
- avisa o advogado no privado com ⚠️ (data, processo, link e o número da agenda).
Se a publicação já tem agenda ligada (ou já existe audiência do processo nesse dia), não faz nada. Se acha
designação mas não consegue ler data e hora com segurança (ou acha mais de uma), não cadastra: só avisa o
advogado para conferir. Não marca a publicação como lida.

Gasto no EasyJur: 3 listagens a cada 2 horas + 1 leitura por publicação nova + 1–2 consultas de agenda por
audiência achada. Privacidade: o log não leva nome, número de processo nem link.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

A_CADA = timedelta(hours=2)
HORAS = range(7, 20)
JANELA_D = 3
TERMOS = {"17065673": "danielle", "17161964": "danielle", "26088398": "fernanda"}
MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
         "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
TITULO = "⚠️🗓️ *AUDIÊNCIA DESIGNADA"
RE_DESIGNA = re.compile(r"design|redesign|remarc|inclu\w* (?:o feito )?em pauta|pautad|fica(?:m)? (?:as partes )?intimad\w* "
                        r"(?:para|da) (?:a )?audiencia|realizar-se-a|sera realizada|a ser realizada")
# o TRT8 às vezes não escreve "audiência": "Inclusão em pauta do dia 22/10/2026 09:00 para tentativa de conciliação"
RE_GATILHO = re.compile(r"audiencia|em pauta|pauta do dia|tentativa de conciliacao|sessao de (?:conciliacao|julgamento)")
RE_DATA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b|\b(\d{1,2}) de (" + "|".join(MESES) + r") de (\d{4})\b")
RE_HORA = re.compile(r"(?<![\d/])(\d{1,2})\s*(?:h|:)\s*(\d{2})?(?:\s*min)?(?!\d)")
RE_LINK = re.compile(r"https?://[^\s<>\"')]+", re.I)
SALAS = ("zoom.us", "teams.microsoft", "teams.live", "webex", "jitsi", "meet.google", "whereby", "balcao", "sala")
_estado = {"ultima": None, "vistos": set()}


def _log(msg):
    print(f"[{datetime.now(timezone(timedelta(hours=-3))):%d/%m %H:%M:%S}] audiências: {msg}", flush=True)


def norm(t):
    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _data(m):
    try:
        if m.group(1):
            a = int(m.group(3))
            return date(a + 2000 if a < 100 else a, int(m.group(2)), int(m.group(1)))
        return date(int(m.group(6)), MESES[m.group(5)], int(m.group(4)))
    except (ValueError, KeyError):
        return None


def achar_audiencias(texto, hoje):
    """[(data, 'HH:MM', tipo)] das audiências DESIGNADAS no texto (datas a partir de hoje), sem repetição."""
    t = norm(texto)
    achadas = []
    for m in RE_GATILHO.finditer(t):
        janela = t[max(0, m.start() - 250): m.end() + 350]
        if not RE_DESIGNA.search(janela):
            continue
        tipo = re.match(r"audiencia\s+(?:de\s+)?(una|inicial|de instrucao|instrucao|de conciliacao|conciliacao|"
                        r"de julgamento|telepresencial|tele-presencial|virtual|presencial|telepresencial)?", t[m.start():])
        tipo = (tipo.group(1) or "").replace("de ", "").strip() if tipo else ""
        for dm in RE_DATA.finditer(janela):
            dia = _data(dm)
            if not dia or dia < hoje or dia > hoje + timedelta(days=400):
                continue
            depois = janela[dm.end(): dm.end() + 40]
            hm = RE_HORA.search(depois)
            if not hm:
                antes = janela[max(0, dm.start() - 40): dm.start()]
                hm = RE_HORA.search(antes)
            if not hm:
                continue
            h, mi = int(hm.group(1)), int(hm.group(2) or 0)
            if 6 <= h <= 20 and mi < 60:
                achadas.append((dia, f"{h:02d}:{mi:02d}", tipo))
    unicas = []
    for a in achadas:
        if (a[0], a[1]) not in [(u[0], u[1]) for u in unicas]:
            unicas.append(a)
    return unicas


def link_da_sala(texto):
    for u in RE_LINK.findall(texto or ""):
        if any(s in u.lower() for s in SALAS):
            return u.rstrip(".,;")
    return ""


def tem_designacao(texto):
    t = norm(texto)
    return bool(RE_GATILHO.search(t)) and bool(RE_DESIGNA.search(t))


def rodada(zaia, easyjur_fn, agora, contagem, d):
    if _estado["ultima"] and agora - _estado["ultima"] < A_CADA:
        return
    local = agora.astimezone(d.BRT)
    if local.hour not in HORAS:
        return
    _estado["ultima"] = agora
    ej = easyjur_fn()
    hoje = local.date()
    advs = {"danielle": d.DANIELLE, "fernanda": d.FERNANDA}
    for termo, quem in TERMOS.items():
        r = ej.chamar("list_publicacoes", idNome=termo, data_disponibilizacao_inicio=(hoje - timedelta(days=JANELA_D)).isoformat(),
                      data_disponibilizacao_fim=hoje.isoformat(), page_size=100) or {}
        for p in r.get("data", []):
            if p.get("id") in _estado["vistos"] or p.get("codPublicacaoVinculada"):
                continue  # cópia de outra publicação: a matriz é tratada
            _estado["vistos"].add(p.get("id"))
            try:
                tratar(zaia, ej, d, p, advs[quem], hoje, contagem)
            except Exception as erro:
                if type(erro).__name__ == "OrcamentoEasyJur":
                    raise
                _log(f"publicação não tratada: {type(erro).__name__}")


def tratar(zaia, ej, d, p, adv, hoje, contagem):
    full = (ej.chamar("get_publicacao", publicacao_id=str(p["id"])) or {}).get("data") or {}
    texto = " ".join(str(full.get(k) or "") for k in ("conteudoPublicacao", "inteiroTeor"))
    if not tem_designacao(texto):
        return
    cod = str(full.get("codPublicacao") or p.get("codPublicacao") or "")
    processo = full.get("processo") or {}
    num = full.get("numProcesso") or p.get("numProcesso") or "processo não informado"
    if ((ej.chamar("list_agenda", cod_publicacao=cod, page_size=5) or {}).get("data") or []):
        return  # já tem agenda ligada a esta publicação
    achadas = achar_audiencias(texto, hoje)
    link = link_da_sala(texto)
    disp = str(p.get("dataDisponibilizacao") or p.get("dataPublicacao") or "")[:10]
    disp_br = f"{disp[8:10]}/{disp[5:7]}" if len(disp) == 10 else disp
    if len(achadas) != 1:
        lista = "; ".join(f"{a[0]:%d/%m/%Y} às {a[1].replace(':', 'h')}" for a in achadas) or "não consegui ler"
        avisar(zaia, d, adv, cod, (
            f"{TITULO} — confira — {num}*\nA publicação de {disp_br} (🔖 P-{cod}) fala em designação de audiência, "
            f"mas a data/hora ficou {'ambígua' if achadas else 'ilegível'} para mim: {lista}.\n"
            + (f"Link da sala (do tribunal): {link}\n" if link else "")
            + "👉 Confira na publicação e cadastre na agenda (ou peça aqui: \"agende audiência ...\")."))
        contagem["audiencias_conferir"] = contagem.get("audiencias_conferir", 0) + 1
        return
    dia, hora, tipo = achadas[0]
    if processo.get("id"):
        mesmas = (ej.chamar("list_agenda", processo=processo["id"], tipo="AUDIENCIA", data_interna_inicio=dia.isoformat(),
                            data_interna_fim=dia.isoformat(), page_size=5) or {}).get("data") or []
        if [i for i in mesmas if i.get("status") != "S"]:
            return  # a equipe já cadastrou
    h, mi = map(int, hora.split(":"))
    fim = f"{min(h + 1, 23):02d}:{mi:02d}"
    rotulo = f"Audiência {tipo}".strip()
    trecho = ""
    m_id = re.search(r"(ID da reuni[aã]o[^\n]{0,40}|senha[^\n]{0,40})", texto, re.I)
    if m_id:
        trecho = " " + m_id.group(0).strip()
    descricao = (f"{rotulo} designada na publicação de {disp_br} (cód. {cod}), processo {num}. "
                 + (f"Link da sala (do tribunal): {link}.{trecho} " if link else "Sem link na publicação: conferir. ")
                 + "Cadastrada automaticamente a partir da publicação — conferir.")
    if d.DRY_RUN:
        _log("[simulação] cadastraria audiência designada")
        return
    args = {"tipo": "AUDIENCIA", "id_advogado": adv["id"], "data": dia.isoformat(), "data_fim": dia.isoformat(),
            "hora_inicio": hora, "hora_fim": fim, "local": link or "Conferir na publicação", "descricao": descricao,
            "codigo_publicacao": cod or None, "processo": processo.get("id")}
    novo = (ej.chamar("create_agenda", **args) or {}).get("data") or {}
    contagem["audiencias_cadastradas"] = contagem.get("audiencias_cadastradas", 0) + 1
    cliente = (processo.get("cliente") or processo.get("nome_cliente") or "") if isinstance(processo, dict) else ""
    avisar(zaia, d, adv, cod, (
        f"{TITULO} — {num}*\n{rotulo} em {d.DIAS_SEMANA[dia.weekday()]}, {dia:%d/%m/%Y} às {hora.replace(':', 'h')}"
        + (f" · {cliente}" if cliente else "") + f"\nPublicação de {disp_br} (🔖 P-{cod})\n"
        + (f"🔗 Link da sala (do tribunal, não é Meet do escritório): {link}\n" if link else
           "🔗 A publicação não traz link da sala: confira no PJe.\n")
        + f"✅ Cadastrada na sua agenda do EasyJur (nº {novo.get('id', '?')}). Confira a data na publicação."))
    _log("audiência designada cadastrada e advogado avisado")


def avisar(zaia, d, adv, cod, texto):
    if d.DRY_RUN:
        return
    try:  # o mesmo aviso não se repete (os plantões recomeçam a cada 6 horas)
        conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=adv["tel"]) or {}).get("conversa") or {}
        msgs = (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []) if conv.get("id") else []
        if any(TITULO in (m.get("content") or "") and f"P-{cod}" in (m.get("content") or "") for m in msgs):
            return
    except Exception:
        pass
    try:
        zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"], texto=texto)
    except Exception as erro:
        _log(f"aviso ao advogado falhou: {type(erro).__name__}")
