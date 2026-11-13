"""Etiqueta "Tráfego Pago" no lead que veio do anúncio, sem IA (pedido da usuária em 13/11/2026).

Quem clica no anúncio do Facebook/Instagram chega com a mensagem pronta do botão (hoje "Olá! Quero sair do meu
emprego e receber todos os meus benefícios"; casos Belmiro e Reginaldo, 13/11) ou conta que viu o anúncio. A Annie
não aplica etiqueta de forma confiável, então o despachante faz: a cada 10 minutos olha as conversas NOVAS dos
últimos 8 dias e põe a etiqueta claude-etiqueta-14 ("Tráfego Pago") quando
  - a 1ª mensagem do cliente é uma das mensagens prontas dos anúncios (FRASES_PRONTAS), ou
  - em uma das 6 primeiras mensagens o cliente cita "anúncio" ou "propaganda".
Só acrescenta a etiqueta (nunca tira nenhuma) e nunca manda mensagem. O funil da semana (funil_semanal.py) conta
os leads do tráfego por essa etiqueta. Mensagem pronta nova de anúncio novo: acrescentar em FRASES_PRONTAS.
O log não leva nome nem telefone.
"""
import re
from datetime import timedelta, timezone

ETIQUETA_ID, ETIQUETA_NOME = "claude-etiqueta-14", "Tráfego Pago"
INTERVALO = timedelta(minutes=10)
JANELA = timedelta(days=8)  # cobre a semana do funil mesmo depois de reiniciar o plantão
ESPERA = timedelta(hours=3)  # depois disso, conversa sem sinal de anúncio não é lida de novo
MAX_LEITURAS = 8  # por volta (a Za.Ia aceita 60 leituras por minuto, divididas com o resto do plantão)
FRASES_PRONTAS = (
    r"quero sair do (meu )?emprego e receber",
    r"receber todos os meus beneficios",
    r"(saber|entender) mais sobre (a )?rescisao indireta",
    r"tenho interesse e queria mais informac",  # texto padrão do botão do Meta
)
RE_PRONTA = re.compile("|".join(FRASES_PRONTAS))
RE_ANUNCIO = re.compile(r"\banuncio|\bpropaganda")

_estado = {"ultima": None, "decididos": set(), "etiquetados": None}


def _txt(m, d):
    return d.sem_acento(m.get("content") or "").lower()


def veio_do_anuncio(msgs, d):
    """True / False pelo que o cliente escreveu (mensagens em qualquer ordem)."""
    cliente = [m for m in sorted(msgs, key=lambda m: m.get("createdAt") or "") if m.get("sender") == "CONTACT"]
    if not cliente:
        return False
    if RE_PRONTA.search(_txt(cliente[0], d)):
        return True
    return any(RE_ANUNCIO.search(_txt(m, d)) for m in cliente[:6])


def etiquetados(zaia):
    """Telefones com a etiqueta Tráfego Pago (até 500)."""
    tels, offset = set(), 0
    while offset < 500:
        r = zaia.chamar("listar_contatos", etiqueta=ETIQUETA_NOME, limit=100, offset=offset) or {}
        cont = r.get("contatos") or r.get("data") or []
        tels |= {re.sub(r"\D", "", c.get("phone") or "") for c in cont}
        if len(cont) < 100:
            return tels - {""}
        offset += 100
    return tels - {""}


def rodada(zaia, agora, contagem, d, dry_run=False):
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    if _estado["etiquetados"] is None:
        _estado["etiquetados"] = etiquetados(zaia)
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    lista = zaia.chamar("listar_conversas", limit=100, periodo={
        "inicio": (agora - JANELA).astimezone(timezone.utc).strftime(fmt),
        "fim": agora.astimezone(timezone.utc).strftime(fmt)}) or {}
    lidas = marcadas = 0
    for at in lista.get("atendimentos", []):
        conv, cont = at.get("conversa") or {}, at.get("contact") or {}
        tel = re.sub(r"\D", "", at.get("phone") or "")
        criada = d.ler_iso(conv["createdAt"]) if conv.get("createdAt") else None
        if (not tel or tel in d.EQUIPE or len(tel) > 13 or not cont.get("id") or not criada
                or criada < agora - JANELA or tel in _estado["etiquetados"] or tel in _estado["decididos"]):
            continue
        if lidas >= MAX_LEITURAS:
            break
        lidas += 1
        msgs = (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", [])
        if veio_do_anuncio(msgs, d):
            if not dry_run:
                zaia.chamar("adicionar_etiqueta_contato", contatoId=cont["id"], etiquetaId=ETIQUETA_ID)
            _estado["etiquetados"].add(tel)
            marcadas += 1
        elif agora - criada > ESPERA:
            _estado["decididos"].add(tel)
    if marcadas:
        contagem["trafego_etiquetado"] = contagem.get("trafego_etiquetado", 0) + marcadas
