"""Gravação no EasyJur das ordens do Secretário geral (linhas "🤖 S[n]") — sem IA, com o token fixo.

Desde 13/11/2026 a rotina Secretário geral não grava mais nada no EasyJur pelo conector do Claude (caiu junto com
todos os conectores no incidente de 13/11). Depois do OK do advogado, ela publica no canal do pedido:

  ✅ S12 aprovado por Dra. Fernanda — ⏳ gravando no EasyJur (o despachante grava em poucos minutos e confirma aqui com 🧾 S12)
  🤖 S12 · AGENDA · tipo ATENDIMENTO · advogado 378457 · data 14/11/2026 · hora 14:00 · fim 14:30 · cliente 681965844 · local Escritório · desc Atendimento trabalhista
  🤖 S13 · REMARCAR · agenda 695043334 · data 15/11/2026 · hora 10:00 · fim 10:30
  🤖 S14 · DESMARCAR · agenda 695043334

Sem o número (conector do EasyJur fora do ar na rotina), o cliente vai pelo nome completo e a agenda pelo
advogado + o horário antigo: "REMARCAR · advogado 378457 · de 14/11/2026 14:00 · data ... · hora ...".

Este módulo roda dentro do plantão do despachante: lê os 5 canais do Secretário, grava, confere e responde no
mesmo canal "🧾 S12 de 13/11 gravado no EasyJur (agenda nº X)". Cada linha leva a marca "[S12 de 13/11 #1]" na
descrição, que impede gravar duas vezes. Erro passageiro tenta de novo; na 3ª falha avisa "⚠️ S12 de 13/11 NÃO
gravado" no canal. Privacidade: repositório público, o log só leva códigos.
"""

import re
from datetime import date, datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
GRUPOS = ["claude-grupo-1", "claude-grupo-17"]
PRIVADOS = ["5594992048054", "5594991742534", "5524992432455"]
ADVOGADOS = {344269, 344268, 378457, 354290, 372515}
TIPOS = {"ATENDIMENTO", "REUNIAO", "AUDIENCIA", "PERICIA", "TAREFA", "COMPROMISSO", "PRAZO", "VIAGEM", "DILIGENCIA"}
INTERVALO = timedelta(minutes=2)
JANELA = timedelta(days=2)
MAX_FALHAS = 3
RE_APROVADO = re.compile(r"✅\s*\*?S(\d+)\*?\s+(?:aprovad|feito)", re.I)
RE_FICHA = re.compile(r"^\s*🤖\s*\*?S(\d+)\*?\s*·\s*(.+?)\s*$", re.M)
RE_FEITO = re.compile(r"(?:🧾|⚠️)\s*\*?S(\d+)\*?\s+de\s+(\d{2})/(\d{2})")
RE_DATA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
RE_HORA = re.compile(r"^(\d{1,2})[:h](\d{2})?$")

_estado = {"ultima": None, "visto": {}, "falhas": {}}


class FichaInvalida(ValueError):
    pass


def ler_iso(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def _sem_acento(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower().strip()


def _data(t):
    m = RE_DATA.search(t)
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except (AttributeError, ValueError):
        raise FichaInvalida(f"data inválida: {t!r}") from None


def _hora(t):
    m = RE_HORA.match(t.strip().lower())
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        raise FichaInvalida(f"hora inválida: {t!r}")
    return f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}"


def ler_ficha(n, resto):
    partes = [p.strip() for p in resto.split("·") if p.strip()]
    op = _sem_acento(partes[0]).upper() if partes else ""
    if op not in ("AGENDA", "REMARCAR", "DESMARCAR"):
        raise FichaInvalida(f"operação desconhecida: {partes[:1]}")
    f = {"s": int(n), "op": op}
    for p in partes[1:]:
        chave, _, valor = p.partition(" ")
        chave, valor = _sem_acento(chave), valor.strip()
        if chave == "tipo":
            if _sem_acento(valor).upper() not in TIPOS:
                raise FichaInvalida(f"tipo desconhecido: {valor!r}")
            f["tipo"] = _sem_acento(valor).upper()
        elif chave in ("advogado", "advogado2", "agenda", "processo", "publicacao"):
            if valor in ("-", "—", ""):
                continue
            if not valor.isdigit():
                raise FichaInvalida(f"{chave} sem número: {valor!r}")
            f[chave] = int(valor)
        elif chave == "cliente":
            if valor in ("-", "—", ""):
                continue
            if valor.isdigit():
                f["cliente"] = int(valor)
            elif len(valor.split()) >= 2:
                f["cliente_nome"] = valor
            else:
                raise FichaInvalida(f"cliente precisa do número ou do nome completo: {valor!r}")
        elif chave == "data":
            f["data"] = _data(valor)
        elif chave == "hora":
            f["hora"] = _hora(valor)
        elif chave == "fim":
            f["fim"] = _hora(valor)
        elif chave == "de":
            d, _, h = valor.partition(" ")
            f["de_data"], f["de_hora"] = _data(d), _hora(h) if h else None
        elif chave == "local":
            f["local"] = valor
        elif chave == "desc":
            f["desc"] = valor
        else:
            raise FichaInvalida(f"campo desconhecido: {p!r}")
    if "advogado" in f and f["advogado"] not in ADVOGADOS:
        raise FichaInvalida(f"advogado desconhecido: {f['advogado']}")
    falta = []
    if op == "AGENDA":
        falta = [c for c in ("tipo", "advogado", "data", "hora", "desc") if c not in f]
    elif "agenda" not in f and not ("advogado" in f and "de_data" in f):
        falta = ["agenda ou advogado + de DD/MM/AAAA HH:MM"]
    if op == "REMARCAR":
        falta += [c for c in ("data", "hora") if c not in f]
    if falta:
        raise FichaInvalida(f"{op} sem {', '.join(falta)}")
    if "hora" in f and "fim" not in f:
        h = datetime.strptime(f["hora"], "%H:%M") + timedelta(minutes=30)
        f["fim"] = f"{h:%H:%M}"
    return f


def pendentes(msgs, agora):
    """{chave "S12 de 13/11": [fichas]} aprovadas com linhas 🤖, ainda sem 🧾/⚠️ da mesma chave no canal."""
    feitas = {f"S{int(n)} de {d}/{m}" for x in msgs if x.get("sender") != "CONTACT"
              for n, d, m in RE_FEITO.findall(x.get("content") or "")}
    pend = {}
    for x in sorted(msgs, key=lambda y: y["createdAt"]):
        texto = x.get("content") or ""
        if x.get("sender") == "CONTACT" or agora - ler_iso(x["createdAt"]) > JANELA:
            continue
        aprovados = {int(n) for n in RE_APROVADO.findall(texto)}
        dia = ler_iso(x["createdAt"]).astimezone(BRT).strftime("%d/%m")
        for ordem, (n, resto) in enumerate(RE_FICHA.findall(texto), 1):
            chave = f"S{int(n)} de {dia}"
            if int(n) not in aprovados or chave in feitas:
                continue
            try:
                ficha = ler_ficha(n, resto)
            except FichaInvalida as e:
                ficha = {"s": int(n), "erro": str(e)}
            ficha["ordem"] = ordem
            pend.setdefault(chave, []).append(ficha)
    return pend


# ---------------------------------------------------------------- EasyJur
def _id(r):
    d = (r or {}).get("data") if isinstance(r, dict) else None
    d = d[0] if isinstance(d, list) and d else d
    return (d or {}).get("id") if isinstance(d, dict) else None


def _itens_do_dia(ej, adv, dia):
    return (ej.chamar("list_agenda", id_responsavel_qualquer=adv, data_interna_inicio=dia.isoformat(),
                      data_interna_fim=dia.isoformat(), page_size=100) or {}).get("data") or []


def _cliente(ej, f):
    if "cliente" in f:
        return f["cliente"]
    if "cliente_nome" not in f:
        return None
    alvo = _sem_acento(re.sub(r"\s+", " ", f["cliente_nome"]))
    achados = [p for p in (ej.chamar("list_pessoas", nome=f["cliente_nome"], page_size=20) or {}).get("data") or []
               if _sem_acento(re.sub(r"\s+", " ", p.get("nome") or "")) == alvo]
    if len(achados) != 1:
        raise RuntimeError(f"cliente pelo nome: {len(achados)} cadastro(s) com esse nome completo no EasyJur")
    return achados[0]["id"]


def _achar_agenda(ej, f):
    if "agenda" in f:
        return f["agenda"]
    itens = [i for i in _itens_do_dia(ej, f["advogado"], f["de_data"]) if i.get("status") != "S"
             and (f.get("de_hora") is None or (i.get("hora_inicio") or "")[:5] == f["de_hora"])]
    if len(itens) != 1:
        raise RuntimeError(f"{len(itens)} compromisso(s) do advogado nesse dia e horário (precisa ser 1)")
    return itens[0]["id"]


def _conflito(ej, adv, dia, hora, fim, menos=None):
    for i in _itens_do_dia(ej, adv, dia):
        if i.get("status") == "S" or i.get("id") == menos:
            continue
        a, b = (i.get("hora_inicio") or "")[:5], (i.get("hora_fim") or "")[:5]
        if a and a != "00:00" and a < fim and (b or a) > hora:
            return f"{a}"
    return None


def executar(ej, chave, f):
    """Grava uma ficha; devolve a frase do 🧾. Erro: exceção (a rodada tenta de novo e avisa na 3ª)."""
    marca = f"[{chave} #{f['ordem']}]"
    if f["op"] == "AGENDA":
        for i in _itens_do_dia(ej, f["advogado"], f["data"]):
            if marca in (i.get("descricao") or ""):
                return f"agenda nº {i.get('id')} já estava gravada"
        conflito = _conflito(ej, f["advogado"], f["data"], f["hora"], f["fim"])
        args = {"tipo": f["tipo"], "id_advogado": f["advogado"], "data": f["data"].isoformat(),
                "data_fim": f["data"].isoformat(), "hora_inicio": f["hora"], "hora_fim": f["fim"],
                "descricao": f"{f['desc']} (criado pelo WhatsApp) {marca}"}
        for k_ficha, k_api in (("advogado2", "id_advogado2"), ("processo", "processo"),
                               ("publicacao", "codigo_publicacao"), ("local", "local")):
            if k_ficha in f:
                args[k_api] = f[k_ficha]
        cliente = _cliente(ej, f)
        if cliente:
            args["cliente"] = cliente
        novo = _id(ej.chamar("create_agenda", **args))
        if not novo:
            ok = [i for i in _itens_do_dia(ej, f["advogado"], f["data"]) if marca in (i.get("descricao") or "")]
            if not ok:
                raise RuntimeError("o EasyJur não confirmou a gravação")
            novo = ok[0].get("id")
        frase = f"agenda nº {novo} ({f['data']:%d/%m} {f['hora']})"
        return frase + (f" ⚠️ já havia outro compromisso às {conflito} nesse dia" if conflito else "")
    aid = _achar_agenda(ej, f)
    try:
        atual = (ej.chamar("get_agenda", agenda_id=aid) or {}).get("data") or {}
    except Exception:  # sem a leitura, grava assim mesmo (update é idempotente)
        atual = {}
    if f["op"] == "DESMARCAR":
        if atual.get("status") == "S":
            return f"agenda nº {aid} já estava desmarcada"
        ej.chamar("update_agenda", agenda_id=aid, status="S")
        return f"agenda nº {aid} desmarcada"
    if atual.get("data") == f["data"].isoformat() and (atual.get("hora_inicio") or "")[:5] == f["hora"]:
        return f"agenda nº {aid} já estava em {f['data']:%d/%m} {f['hora']}"
    adv = f.get("advogado") or atual.get("id_advogado") or (atual.get("advogado") or {}).get("id")
    conflito = _conflito(ej, adv, f["data"], f["hora"], f["fim"], menos=aid) if adv else None
    ej.chamar("update_agenda", agenda_id=aid, data=f["data"].isoformat(), data_fim=f["data"].isoformat(),
              hora_inicio=f["hora"], hora_fim=f["fim"])
    frase = f"agenda nº {aid} remarcada para {f['data']:%d/%m} {f['hora']}"
    return frase + (f" ⚠️ já havia outro compromisso às {conflito} nesse dia" if conflito else "")


# ---------------------------------------------------------------- canais e rodada
def _canais(zaia, conversas_lidas):
    """[(canal, mensagens)] — grupos sempre; privado só quando mudou desde a última leitura."""
    saida = []
    for g in GRUPOS:
        saida.append((g, (zaia.chamar("ler_grupo", grupoId=g, limit=40) or {}).get("mensagens", [])))
    for tel in PRIVADOS:
        msgs = (conversas_lidas or {}).get(tel)
        if msgs is None:
            conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=tel) or {}).get("conversa") or {}
            ultima = conv.get("lastMessageAt")
            if not ultima or _estado["visto"].get(tel) == ultima:
                continue
            msgs = (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", [])
            _estado["visto"][tel] = ultima
        saida.append((tel, msgs))
    return saida


def _responder(zaia, canal, texto):
    if canal.startswith("claude-grupo"):
        zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=canal, texto=texto)
    else:
        zaia.chamar("enviar_mensagem", assinatura="ia", numero=canal, texto=texto)


def rodada(zaia, easyjur_fn, agora=None, log=print, conversas_lidas=None, dry_run=False):
    agora = agora or datetime.now(timezone.utc)
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return 0
    _estado["ultima"] = agora
    feitos = 0
    for canal, msgs in _canais(zaia, conversas_lidas):
        for chave, fichas in pendentes(msgs, agora).items():
            erros = [x["erro"] for x in fichas if "erro" in x]
            if erros:
                if not dry_run:
                    _responder(zaia, canal, f"⚠️ {chave} NÃO gravado no EasyJur — linha 🤖 fora do formato: "
                                            f"{erros[0][:150]}. A agenda do Google e a Za.Ia não mudam; "
                                            f"refaça o pedido ou responda EDITAR {chave.split()[0]}.")
                log(f"secretário: {chave.split()[0]} com linha inválida")
                continue
            if dry_run:
                log(f"[simulação] secretário: gravaria {chave.split()[0]} ({len(fichas)} linha(s))")
                continue
            try:
                ej = easyjur_fn()
                frases = [executar(ej, chave, f) for f in fichas]
            except Exception as erro:
                n = _estado["falhas"][chave] = _estado["falhas"].get(chave, 0) + 1
                log(f"secretário: {chave.split()[0]} falhou ({type(erro).__name__}), tentativa {n}")
                if n >= MAX_FALHAS:
                    _responder(zaia, canal, f"⚠️ {chave} NÃO gravado no EasyJur depois de {n} tentativas — "
                                            f"{str(erro)[:160]}. Confira na agenda do EasyJur ou peça de novo.")
                continue
            _responder(zaia, canal, f"🧾 {chave} gravado no EasyJur: " + "; ".join(frases))
            _estado["falhas"].pop(chave, None)
            feitos += 1
            log(f"secretário: {chave.split()[0]} gravado ({len(fichas)} linha(s))")
    return feitos
