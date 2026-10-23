"""Comprovante de pagamento enviado pelo CLIENTE ao número do escritório — sem IA (pedido da usuária, 23/10/2026).

Roda dentro do plantão do despachante, a cada 5 minutos. Olha as conversas de clientes com mensagem
nos últimos minutos e procura imagem/PDF que a Za.Ia descreveu como comprovante de Pix, transferência,
depósito ou boleto pago PARA o escritório (Dra. Danielle, Dr. Lucas ou Dra. Fernanda como recebedor) — ou
comprovante de pagamento sem recebedor legível, quando o cliente fala em pagamento perto dele.

Para cada comprovante novo, publica no grupo "Financeiro Escritório" o aviso 🧾 COMPROVANTE DE CLIENTE
(nome, telefone, hora e o que a Za.Ia leu, sem CPF, agência nem conta) e acorda a rotina financeira.
A rotina confere o cadastro do cliente e as receitas no nome dele no EasyJur, diz no grupo qual receita
bate com o valor e publica o rascunho (BAIXA F / LANÇAMENTO F). Nada é lançado sem o OK de um advogado.

Privacidade: o log não leva nome, telefone nem valor.
"""

import re
from datetime import datetime, timedelta, timezone

COMECO = datetime(2026, 10, 23, 20, 0, tzinfo=timezone.utc)   # só comprovantes a partir da entrada no ar
INTERVALO = timedelta(minutes=5)
JANELA_CONVERSAS = timedelta(minutes=20)
JANELA_MSG = timedelta(hours=24)
GRUPO_FINANCEIRO = "claude-grupo-18"
TITULO = "🧾 *COMPROVANTE DE CLIENTE"
RE_PAGAMENTO = re.compile(r"comprovante|pix|transferencia|deposito|ted\b|doc\b|boleto pago|pagamento efetuado|"
                          r"pagamento realizado|transacao")
RE_VALOR = re.compile(r"R\$\s*\d")
RE_ESCRITORIO = re.compile(r"danielle|esteves|seoane|fernanda mesquita|lucas martins")
RE_CLIENTE_PAGOU = re.compile(r"\b(paguei|pago|pagamento|comprovante|pix|transferi|depositei|parcela|entrada|"
                              r"honorario|mensalidade|boleto)\b")
_estado = {"ultima": None, "avisados": set()}


def _log(msg):
    print(f"[{datetime.now(timezone(timedelta(hours=-3))):%d/%m %H:%M:%S}] comprovantes: {msg}", flush=True)


def limpar(desc):
    """Tira da descrição o que não precisa ir ao grupo: CPF/CNPJ, agência, conta e o rodapé do banco."""
    t = re.sub(r"\((?:CPF|CNPJ)[^)]*\)", "", desc or "")
    t = re.sub(r",?\s*(?:com\s+)?(?:CPF|CNPJ)(?:/CNPJ)?(?:\s+final)?\s*[\d.*\-/]+[\d*\-]*", "", t)
    t = re.sub(r",?\s*ag[eê]ncia\s*[\d\-]+", "", t, flags=re.I)
    t = re.sub(r",?\s*conta\s*(?:corrente|de pagamentos|poupan[cç]a)?\s*[\d\-]{4,}", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:420] + "…") if len(t) > 420 else t


def tipo_de_comprovante(desc, textos_do_cliente, sem_acento):
    """'escritorio' (pagamento ao escritório), 'provavel' (comprovante sem recebedor legível, e o cliente fala em
    pagamento) ou None. Comprovante de salário, de compra etc. (recebedor de fora) não conta."""
    sa = sem_acento(desc)
    if not (RE_PAGAMENTO.search(sa) and RE_VALOR.search(desc or "")):
        return None
    if not re.search(r"comprovante|pix|transferencia|deposito|ted\b|transacao", sa):
        return None
    recebedor = re.search(r"(?:destinatari[oa]|recebedor|favorecid[oa]|beneficiari[oa])\s*(?:e|:)?\s*([^.,;]{3,60})", sa)
    if recebedor:
        return "escritorio" if RE_ESCRITORIO.search(recebedor.group(1)) else None
    if RE_ESCRITORIO.search(sa):
        return "escritorio"
    if any(RE_CLIENTE_PAGOU.search(sem_acento(t)) for t in textos_do_cliente):
        return "provavel"
    return None


def marca(msg):
    return "#" + re.sub(r"\D", "", msg.get("id", ""))[-8:]


def rodada(zaia, agora, contagem, d, acordar_financeiro=None):
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    inicio = (_estado["ultima"] or agora) - JANELA_CONVERSAS
    _estado["ultima"] = agora
    lista = zaia.chamar("listar_conversas", limit=60, periodo={
        "inicio": inicio.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "fim": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}) or {}
    achados = []
    for at in lista.get("atendimentos", []):
        conv = at.get("conversa") or {}
        tel = (at.get("phone") or "").strip()
        if not tel or tel in d.EQUIPE or not conv.get("id"):
            continue
        msgs = sorted((zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []),
                      key=lambda m: m["createdAt"])
        for i, m in enumerate(msgs):
            quando = d.ler_iso(m["createdAt"])
            if (m.get("sender") != "CONTACT" or m.get("contentType") not in ("IMAGE", "DOCUMENT")
                    or quando < COMECO or agora - quando > JANELA_MSG or m["id"] in _estado["avisados"]):
                continue
            perto = [x.get("content") or "" for x in msgs if x.get("sender") == "CONTACT" and x is not m
                     and abs(d.ler_iso(x["createdAt"]) - quando) <= timedelta(minutes=10)]
            tipo = tipo_de_comprovante(m.get("content"), perto, d.sem_acento)
            if tipo:
                nome = (at.get("contact") or {}).get("name") or at.get("name") or ""
                achados.append((m, tipo, nome, tel, perto))
    if not achados:
        return
    grupo = (zaia.chamar("ler_grupo", grupoId=GRUPO_FINANCEIRO, limit=100) or {}).get("mensagens", [])
    ja = "\n".join(x.get("content") or "" for x in grupo)
    novos = 0
    for m, tipo, nome, tel, perto in achados:
        if marca(m) in ja:
            _estado["avisados"].add(m["id"])
            continue
        hora = d.ler_iso(m["createdAt"]).astimezone(d.BRT)
        fala = next((t for t in perto if t.strip() and not t.startswith("[")), "")
        texto = (f"{TITULO} — {nome} ({tel})*\n"
                 f"Chegou na conversa do escritório em {hora:%d/%m} às {hora:%H}h{hora:%M}"
                 + (" (recebedor não aparece na imagem: confira se é pagamento ao escritório)" if tipo == "provavel" else "")
                 + f".\nO que a Za.Ia leu: _{limpar(m.get('content'))}_"
                 + (f"\nO cliente escreveu: \"{fala[:160]}\"" if fala else "")
                 + "\n⏳ Vou conferir o cadastro e as receitas dele no EasyJur e publico aqui qual parcela bate com o "
                   f"valor, para o OK de um advogado antes de lançar. {marca(m)}")
        contagem["comprovantes"] = contagem.get("comprovantes", 0) + 1
        if d.DRY_RUN:
            _log("[simulação] avisaria comprovante de cliente no grupo do financeiro")
            continue
        zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=GRUPO_FINANCEIRO, texto=texto)
        _estado["avisados"].add(m["id"])
        novos += 1
    if novos:
        _log(f"{novos} comprovante(s) de cliente avisado(s) no grupo do financeiro")
        if acordar_financeiro:
            acordar_financeiro()
