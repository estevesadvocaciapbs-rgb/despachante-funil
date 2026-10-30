"""Lead de caso prioritário que hesita: aviso imediato no grupo Firma 2026, sem IA (pedido da usuária, caso de 30/10).

Casos prioritários: gestante, acidente de trabalho, assédio sexual, auxílio-acidente e maternidade. Quando um lead
desses fala em distância, atendimento presencial, valor, Defensoria, outro advogado, desistência ou indecisão, a
Annie não resolve: precisa de resposta humana na hora. Roda no plantão a cada 3 minutos, só olha conversa com
movimento recente e avisa uma vez por contato. O log não leva nome nem telefone (repositório público).
"""

import re
from datetime import timedelta

INTERVALO = timedelta(minutes=3)
JANELA = timedelta(minutes=30)      # frase de lead dos últimos 30 minutos
CONVERSA_MAX = timedelta(days=45)   # inclui quem hesita depois da reunião, antes de assinar
MARCA = "🚨 *LEAD EM DÚVIDA"
CIDADES_LOCAIS = "parauapebas|maraba|canaa|curionopolis|eldorado"

TEMAS = [
    ("gestante", r"gestante|gravid"),
    ("assédio sexual", r"assedio sexual|importunacao|passou a mao"),
    ("auxílio-acidente", r"auxilio.?acidente"),
    ("acidente de trabalho", r"acidente|machuquei|me machuc|(bati|cai|cortei|quebrei)\b.{0,40}\btrabalho|"
                             r"\btrabalho\b.{0,40}\b(bati|cai|cortei|quebrei)\b"),
    ("maternidade", r"maternidade"),
]
RE_RECUSA = re.compile(r"defensoria|outr[oa] advogad|ja tenho advogad|desist|nao quero mais|deixa pra la|deixa quieto|"
                       r"nao vou (mais|fazer|fechar|assinar|querer)|nao tenho interesse|nao precisa mais")
MOTIVOS = [
    ("desistência, Defensoria ou outro advogado", RE_RECUSA),
    ("distância ou outra cidade", re.compile(r"\blonge\b|distancia|outra cidade|outro estado|nao sou da[iq]|"
                                             rf"\b(sou de|moro em) (?!{CIDADES_LOCAIS})\w+|"
                                             rf"^e de (?!{CIDADES_LOCAIS})\w+")),
    ("quer atendimento presencial", re.compile(r"presencial|pessoalmente|ir ai\b|ir no escritorio")),
    ("valor ou pagamento", re.compile(r"(muito|ta|esta) caro|nao tenho (dinheiro|condic|como pagar)|"
                                      r"nao posso pagar|sem (dinheiro|condic)")),
    ("indecisão", re.compile(r"vou pensar|preciso pensar|vou analisar|depois (eu )?(falo|vejo|retorno)|nao sei se|"
                             r"em duvida|tenho medo|nao confio|golpe")),
]
_estado = {"ultima": None}
_avisados = set()  # telefones já conferidos neste plantão
_vistos = {}       # conversa -> última movimentação já lida (não relê conversa sem novidade)


def motivo(texto, d):
    t = d.sem_acento(texto).strip()
    return next((nome for nome, rx in MOTIVOS if rx.search(t)), None)


def recusou(msgs, d):
    """True se uma das 3 últimas falas do lead é recusa clara: o follow-up automático deve parar."""
    falas = [m for m in msgs if m.get("sender") == "CONTACT"][-3:]
    return any(RE_RECUSA.search(d.sem_acento(m.get("content"))) for m in falas)


def tema(msgs, d):
    """Tema prioritário pelo que o LEAD disse (a pergunta da Annie cita acidente e gravidez para todo mundo)."""
    t = d.sem_acento(" ".join(m.get("content") or "" for m in msgs if m.get("sender") == "CONTACT"))
    return next((nome for nome, rx in TEMAS if re.search(rx, t)), None)


def rodada(zaia, agora, contagem, d):
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    lista = zaia.chamar("listar_conversas", limit=100, periodo={
        "inicio": (agora - JANELA).astimezone(d.timezone.utc).strftime(fmt),
        "fim": agora.astimezone(d.timezone.utc).strftime(fmt)}) or {}
    grupo = None
    for at in lista.get("atendimentos", []):
        conv = at.get("conversa") or {}
        tel = (at.get("phone") or "").strip()
        # a listagem já vem filtrada pelo período; conversa.lastMessageAt pode estar horas atrasado (visto em 30/10)
        if (conv.get("status") not in ("OPEN", "ASSIGNED") or not tel or tel in d.EQUIPE or tel in _avisados
                or not conv.get("id") or not conv.get("createdAt")
                or agora - d.ler_iso(conv["createdAt"]) > CONVERSA_MAX
                or _vistos.get(conv["id"]) == at.get("lastMessageAt")):
            continue
        _vistos[conv["id"]] = at.get("lastMessageAt")
        msgs = sorted((zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []),
                      key=lambda m: m["createdAt"])
        frases = [(m, motivo(m.get("content"), d)) for m in msgs if m.get("sender") == "CONTACT"
                  and agora - d.ler_iso(m["createdAt"]) <= JANELA]
        frases = [(m, q) for m, q in frases if q]
        area = tema(msgs, d) if frases else None
        if not area:
            continue
        m, por_que = frases[-1]
        if any(d.escrita_por_humano(x) and x["createdAt"] > m["createdAt"] for x in msgs):
            continue  # alguém da equipe já respondeu depois da frase
        _avisados.add(tel)
        grupo = grupo or zaia.chamar("ler_grupo", grupoId=d.GRUPO, limit=100) or {}
        if any(MARCA in (x.get("content") or "") and tel in (x.get("content") or "") for x in grupo.get("mensagens", [])):
            continue  # já avisado (outro plantão)
        contagem["hesitacoes"] = contagem.get("hesitacoes", 0) + 1
        nome = (at.get("contact") or {}).get("name") or at.get("name") or "Lead"
        if d.DRY_RUN:
            d.log("[simulação] avisaria lead em dúvida no grupo")
            continue
        zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=d.GRUPO, texto=(
            f"{MARCA} — {nome} ({tel})*\n"
            f"Caso prioritário: {area}\nMotivo: {por_que}\n"
            f"Disse: \"{(m.get('content') or '')[:200]}\"\n"
            "👉 Precisa de resposta humana agora. Alguém chama este lead?"))
        d.log("lead prioritário em dúvida — avisado no grupo")
