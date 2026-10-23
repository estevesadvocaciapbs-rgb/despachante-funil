"""Testes do resgate (cliente que não veio à reunião), do pedido de avaliação e do aviso de comprovante.

Dados inventados; não acessa nenhum sistema.
"""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("TELEFONES_EQUIPE", "5594992048054,5594991742534,5524992432455")
import despachante as d
import resgate as r
import comprovantes as c

UTC = timezone.utc
TEL = "5594900000123"


def m(sender, texto, quando, tipo="CHAT", i=[0]):
    i[0] += 1
    return {"id": f"claude-mensagem-{9000 + i[0]}", "sender": sender, "content": texto,
            "createdAt": quando.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "contentType": tipo}


class Z:
    def __init__(s, conversas=None, grupo=None, lista=None):
        s.env, s.conversas, s.grupo, s.lista = [], conversas or {}, grupo or [], lista or []

    def chamar(s, f, **a):
        s.env.append((f, a))
        if f == "buscar_conversa_por_telefone":
            conv = s.conversas.get(a["telefone"], (None, []))[0]
            return {"conversa": conv}
        if f == "ler_conversa":
            for conv, msgs in s.conversas.values():
                if conv and conv["id"] == a["conversaId"]:
                    return {"messages": msgs}
        if f == "ler_grupo":
            return {"mensagens": s.grupo}
        if f == "listar_conversas":
            return {"atendimentos": s.lista}
        return {}


class EJ:
    def __init__(s, itens):
        s.itens, s.env = itens, []

    def chamar(s, f, **a):
        s.env.append((f, a))
        if f == "list_agenda":
            return {"data": s.itens, "meta": {"total_pages": 1}}
        return {}


class Ag:
    def livres(s, adv, reservados):
        return [datetime(2026, 10, 27, 9, 30, tzinfo=d.BRT), datetime(2026, 10, 27, 14, 30, tzinfo=d.BRT)]


class Conv:
    def __init__(s, z):
        s.z = z

    def de(s, tel):
        return s.z.conversas.get(tel, (None, []))


def item(data="2026-10-26", hora="14:00", status="A", adv=d.FERNANDA["id"]):
    return {"id": 1, "data": data, "hora_inicio": hora, "hora_fim": "14:30", "status": status, "id_advogado": adv,
            "descricao": f"Reunião com lead — Ana Teste ({TEL}). Agendada automaticamente (A Annie confirmou). "
                         "Link da videochamada: https://meet.google.com/x . Família: guarda do filho."}


CONV = {"id": "claude-conversa-1", "status": "OPEN", "contact": {"id": "claude-contato-1", "name": "Ana Teste"}}
REUNIAO = datetime(2026, 10, 26, 14, 0, tzinfo=d.BRT)  # segunda


def rodar(msgs, agora, itens=None, pendentes=()):
    r._estado.update(ultima=None, ativos={}, avisados=set())
    z = Z({TEL: (CONV, msgs)})
    cont = {}
    leads = r.rodada(z, lambda: EJ(itens or [item()]), lambda: Ag(), Conv(z), agora, cont, d, pendentes)
    return z, leads


antes = [m("AGENT", "*Annie*:\nBom dia, Ana! Passando para lembrar do seu atendimento de hoje, às 14h00, com a dra. "
                    "Fernanda Mesquita, por videochamada.", REUNIAO - timedelta(hours=6)),
         m("AGENT", "*Annie*:\nOlá, Ana! Passando para confirmar nosso atendimento de hoje às 14h00 com a dra. "
                    "Fernanda Mesquita. Podemos confirmar sua presença?", REUNIAO - timedelta(hours=1))]

# 1 hora depois da reunião: ainda espera
z, _ = rodar(antes, REUNIAO + timedelta(hours=1))
assert not [f for f, a in z.env if f == "agendar_mensagem"]

# 2 horas depois, sem sinal: R1 com 2 horários da mesma advogada + aviso no privado dela
z, leads = rodar(antes, REUNIAO + timedelta(hours=2, minutes=5))
env = [a for f, a in z.env if f == "agendar_mensagem"]
assert len(env) == 1 and r.MARCA in env[0]["mensagem"] and d.MARCA_OFERTA in env[0]["mensagem"], env
assert "Fernanda" in env[0]["mensagem"] and "Danielle" not in env[0]["mensagem"]
assert "27/10 às 09:30" in env[0]["mensagem"] and "26/10 (14h00)" in env[0]["mensagem"]
assert d.RE_SLOT.findall(env[0]["mensagem"]) == [("27", "10", "09", "30"), ("27", "10", "14", "30")]  # reunião antiga não vira horário ofertado
assert "?" in env[0]["mensagem"] and env[0]["ativarIaAoResponder"] is True
priv = [a for f, a in z.env if f == "enviar_mensagem"]
assert priv and priv[0]["numero"] == d.FERNANDA["tel"] and r.AVISO_ADV in priv[0]["texto"]
assert leads and leads[0]["tel"] == TEL and leads[0]["texto"].startswith("Família")
print("OK — R1 duas horas depois da reunião sem sinal, com aviso ao advogado")

# fim de semana e fora do horário: não manda
z, _ = rodar(antes, datetime(2026, 10, 26, 21, 0, tzinfo=d.BRT))
assert not [f for f, a in z.env if f == "agendar_mensagem"]

# reunião concluída, reunião nova marcada, equipe falou, contrato ou desistência: não manda
for itens in ([item(status="C")], [item(), item(data="2026-10-30", hora="09:30")]):
    z, _ = rodar(antes, REUNIAO + timedelta(hours=3), itens)
    assert not [f for f, a in z.env if f == "agendar_mensagem"], itens
for extra in (m("USER", "*Dra. Fernanda Mesquita*:\nAna, te liguei agora.", REUNIAO + timedelta(minutes=40)),
              m("AGENT", "*Annie*:\nSegue o contrato pelo ZapSign: https://app.zapsign.com.br/x", REUNIAO + timedelta(hours=1)),
              m("CONTACT", "não tenho mais interesse, obrigada", REUNIAO + timedelta(hours=1))):
    z, _ = rodar(antes + [extra, m("AGENT", "*Annie*:\nCerto!", REUNIAO + timedelta(hours=1, minutes=2))],
                 REUNIAO + timedelta(hours=3))
    assert not [f for f, a in z.env if f == "agendar_mensagem"], extra["content"]
# cliente esperando resposta: não manda (é pendência da equipe)
z, _ = rodar(antes + [m("CONTACT", "oi, desculpa", REUNIAO + timedelta(hours=1))], REUNIAO + timedelta(hours=3))
assert not [f for f, a in z.env if f == "agendar_mensagem"]
# cancelado no EasyJur por falta de retorno (lembretes sem resposta) também entra
z, _ = rodar(antes, REUNIAO + timedelta(hours=3), [item(status="S")])
assert [f for f, a in z.env if f == "agendar_mensagem"] and "não respondeu à confirmação" in \
    [a for f, a in z.env if f == "enviar_mensagem"][0]["texto"]
# regra da usuária (23/10): reunião cancelada pelo advogado não entra — sem lembrete no dia (cancelada antes),
# cliente que respondeu no dia (confirmou ou avisou) ou escritório avisando cancelamento/remarcação
for msgs_dia in ([],
                 antes + [m("CONTACT", "confirmo, obrigada", REUNIAO - timedelta(minutes=50)),
                          m("AGENT", "*Annie*:\nPerfeito!", REUNIAO - timedelta(minutes=49))],
                 [m("CONTACT", "bom dia", REUNIAO - timedelta(hours=7))] + antes,
                 antes + [m("AGENT", "*Annie*:\nAna, a Dra. Fernanda precisou cancelar a reunião de hoje e vai remarcar.",
                            REUNIAO - timedelta(minutes=30))]):
    z, _ = rodar(msgs_dia, REUNIAO + timedelta(hours=3), [item(status="S")])
    assert not [f for f, a in z.env if f == "agendar_mensagem"], msgs_dia
# reunião anterior à entrada no ar: não chama
z, _ = rodar(antes, datetime(2026, 10, 23, 18, 0, tzinfo=d.BRT), [item(data="2026-10-22")])
assert not [f for f, a in z.env if f == "agendar_mensagem"]
print("OK — não chama quando a reunião aconteceu, foi remarcada, a equipe assumiu ou o cliente desistiu")

# cadência: R2, R3 e R4 em 3, 5 e 10 dias úteis depois da reunião (segunda 26/10 → qui 29/10, seg 02/11, seg 09/11)
r1 = m("AGENT", "*Annie*:\nOi, Ana! ... " + r.MARCA + " ... Tenho estes horários:\n\n• terça-feira, 27/10 às 09:30",
       REUNIAO + timedelta(hours=2))
z, leads = rodar(antes + [r1], REUNIAO + timedelta(days=2, hours=1))  # quarta: ainda não
assert not [f for f, a in z.env if f == "agendar_mensagem"] and leads  # mas segue na confirmação
z, _ = rodar(antes + [r1], REUNIAO + timedelta(days=3, minutes=5))  # quinta 29/10 14h05: 3 dias úteis
env = [a for f, a in z.env if f == "agendar_mensagem"]
assert len(env) == 1 and "Passando de novo" in env[0]["mensagem"], env
assert not [f for f, a in z.env if f == "enviar_mensagem"]  # aviso ao advogado só no R1
r2 = m("AGENT", "*Annie*:\nOi, Ana! Passando de novo " + r.MARCA, REUNIAO + timedelta(days=3))
z, _ = rodar(antes + [r1, r2], REUNIAO + timedelta(days=6, hours=-1))  # domingo/segunda cedo: ainda não
assert not [f for f, a in z.env if f == "agendar_mensagem"]
z, _ = rodar(antes + [r1, r2], REUNIAO + timedelta(days=7, minutes=5))  # segunda 02/11: 5 dias úteis
assert "Ainda quer ajuda" in [a for f, a in z.env if f == "agendar_mensagem"][0]["mensagem"]
r3 = m("AGENT", "*Annie*:\nOi, Ana! Ainda quer ajuda? " + r.MARCA, REUNIAO + timedelta(days=7))
z, _ = rodar(antes + [r1, r2, r3], REUNIAO + timedelta(days=14, minutes=5))  # segunda 09/11: 10 dias úteis
assert "última mensagem" in [a for f, a in z.env if f == "agendar_mensagem"][0]["mensagem"]
# cliente respondeu ao R1 e sumiu: o R2 espera também 2 dias úteis depois da resposta
resp = m("CONTACT", "vou ver e te falo", REUNIAO + timedelta(days=2, hours=3))   # quarta 28/10
ok = m("AGENT", "*Annie*:\nCombinado!", REUNIAO + timedelta(days=2, hours=3, minutes=1))
z, _ = rodar(antes + [r1, resp, ok], REUNIAO + timedelta(days=3, minutes=5))  # quinta: ainda não
assert not [f for f, a in z.env if f == "agendar_mensagem"]
z, _ = rodar(antes + [r1, resp, ok], REUNIAO + timedelta(days=4, hours=4))  # sexta 30/10 17h59
assert [f for f, a in z.env if f == "agendar_mensagem"]
# depois de 4 convites: para e avisa o advogado 5 dias úteis depois do último
quatro = [m("AGENT", "*Annie*:\n" + r.MARCA, REUNIAO + timedelta(days=k, hours=2)) for k in (0, 3, 7, 14)]
z, _ = rodar(antes + quatro, REUNIAO + timedelta(days=17, hours=2))
assert not [f for f, a in z.env if f == "agendar_mensagem"] and not [f for f, a in z.env if f == "enviar_mensagem"]
z, _ = rodar(antes + quatro, REUNIAO + timedelta(days=21, hours=3))
assert r.AVISO_FIM in [a for f, a in z.env if f == "enviar_mensagem"][0]["texto"]
print("OK — cadência do resgate (3, 5 e 10 dias úteis) e aviso final")

# cliente que AVISOU no dia que não pode: novos horários logo depois do aviso (a reunião ainda nem passou)
aviso = m("CONTACT", "Bom dia! Não vou poder ir hoje, surgiu um imprevisto no trabalho", REUNIAO - timedelta(hours=5))
resposta = m("AGENT", "*Annie*:\nSem problema, Ana! Vou avisar a Dra. Fernanda.", REUNIAO - timedelta(hours=5) + timedelta(minutes=1))
z, _ = rodar(antes[:1] + [aviso], REUNIAO - timedelta(hours=5) + timedelta(minutes=10))  # 10 min: espera
assert not [f for f, a in z.env if f == "agendar_mensagem"]
z, leads = rodar(antes[:1] + [aviso, resposta], REUNIAO - timedelta(hours=4, minutes=40))
env = [a for f, a in z.env if f == "agendar_mensagem"]
assert len(env) == 1 and "Sem problema, imprevistos acontecem" in env[0]["mensagem"] and r.MARCA in env[0]["mensagem"], env
priv = [a for f, a in z.env if f == "enviar_mensagem"]
assert priv and "avisou que não vai poder" in priv[0]["texto"] and "imprevisto no trabalho" in priv[0]["texto"]
assert leads and leads[0]["tel"] == TEL
# mesmo sem resposta da Annie (último é o aviso do cliente), o R1 sai
z, _ = rodar(antes[:1] + [aviso], REUNIAO - timedelta(hours=4, minutes=40))
assert [f for f, a in z.env if f == "agendar_mensagem"]
# depois do R1, R2 em 3 dias úteis; a resposta da Annie com "remarcar" depois do aviso não conta como cancelamento do escritório
r1a = m("AGENT", "*Annie*:\nOi, Ana! Sem problema, imprevistos acontecem. Já te mando novos horários " + r.MARCA,
        REUNIAO - timedelta(hours=4, minutes=39))
remarca = m("AGENT", "*Annie*:\nVamos remarcar, sim!", REUNIAO - timedelta(hours=4, minutes=38))
z, _ = rodar(antes[:1] + [aviso, resposta, r1a, remarca], REUNIAO + timedelta(days=3, minutes=5))
assert "Passando de novo" in [a for f, a in z.env if f == "agendar_mensagem"][0]["mensagem"]
# aviso com desistência: não chama
z, _ = rodar(antes[:1] + [m("CONTACT", "não vou poder, não tenho mais interesse", REUNIAO - timedelta(hours=5)), resposta],
             REUNIAO - timedelta(hours=4))
assert not [f for f, a in z.env if f == "agendar_mensagem"]
print("OK — cliente que avisou no dia que não pode recebe novos horários e a mesma cadência")

# a resposta ao resgate passa pela confirmação normal: escolheu → grava a reunião nova
assert r.resumo_do_atendimento(item()["descricao"]) == "Família: guarda do filho."
print("OK — resumo do atendimento sem o cabeçalho")

# ---------------------------------------------------------------- avaliação no Google
conv_c = dict(CONV)
msgs_c = [m("AGENT", "*Annie*:\nLembrete", REUNIAO - timedelta(hours=1))]
zc = Z({TEL: (conv_c, msgs_c)})
it_c = dict(item(status="C"), data_conclusao="2026-10-26", id=77)
d._avaliados.clear()
assert d.enviar_avaliacao(zc, conv_c, msgs_c, it_c, d.FERNANDA, TEL, REUNIAO + timedelta(hours=2), {})
env = [a for f, a in zc.env if f == "enviar_mensagem"]
assert env and d.AVALIACAO_LINK in env[0]["texto"] and "Fernanda" in env[0]["texto"] and "Oi, Ana!" in env[0]["texto"]
zc.env.clear()
assert d.enviar_avaliacao(zc, conv_c, msgs_c, it_c, d.FERNANDA, TEL, REUNIAO + timedelta(hours=3), {}) and not zc.env
d._avaliados.clear()  # já tem o link na conversa: não manda de novo
assert d.enviar_avaliacao(zc, conv_c, msgs_c + [m("AGENT", "*Annie*:\n" + d.AVALIACAO_LINK, REUNIAO + timedelta(hours=1))],
                          it_c, d.FERNANDA, TEL, REUNIAO + timedelta(hours=3), {}) and not zc.env
d._avaliados.clear()  # à noite espera a manhã
assert not d.enviar_avaliacao(zc, conv_c, msgs_c, it_c, d.FERNANDA, TEL, datetime(2026, 10, 26, 22, 0, tzinfo=d.BRT), {})
assert not zc.env
d._avaliados.clear()  # concluído antes da entrada no ar: não manda
assert d.enviar_avaliacao(zc, conv_c, msgs_c, dict(it_c, data_conclusao="2026-10-20"), d.FERNANDA, TEL,
                          REUNIAO + timedelta(hours=3), {}) and not zc.env
print("OK — pedido de avaliação no Google depois do atendimento concluído")

# ---------------------------------------------------------------- comprovante de cliente
sa = d.sem_acento
pix_esc = ("Comprovante de transferência Pix realizada em 26 de outubro de 2026 às 10:04, no valor de R$ 300,00. "
           "O destinatário é Danielle Martins Esteves Moreira (CPF final 397-**) da instituição NU PAGAMENTOS - IP, "
           "agência 0001, conta 19621586-9. O pagador é Ana Teste.")
pix_outro = ("Comprovante de transferência Pix no valor de R$ 1.200,00. O destinatário é Ana Teste (CPF final 111-**). "
             "O pagador é Transportes Exemplo Ltda.")  # salário que a cliente mandou como prova do caso
pix_sem = "Comprovante de Pix no valor de R$ 300,00 realizado em 26/10/2026 às 10:04, ID E123."
assert c.tipo_de_comprovante(pix_esc, [], sa) == "escritorio"
assert c.tipo_de_comprovante(pix_outro, ["segue o comprovante do salário"], sa) is None
assert c.tipo_de_comprovante(pix_sem, ["paguei a parcela"], sa) == "provavel"
assert c.tipo_de_comprovante(pix_sem, ["olha isso"], sa) is None
assert c.tipo_de_comprovante("Foto de um RG frente e verso.", ["segue"], sa) is None
limpo = c.limpar(pix_esc)
assert "CPF" not in limpo and "19621586" not in limpo and "0001" not in limpo and "R$ 300,00" in limpo, limpo

agora_c = datetime(2026, 10, 26, 13, 10, tzinfo=UTC)
img = m("CONTACT", pix_esc, agora_c - timedelta(minutes=3), "IMAGE")
txt = m("CONTACT", "segue o pagamento da parcela", agora_c - timedelta(minutes=2))
zf = Z({TEL: (CONV, [img, txt])}, grupo=[],
       lista=[{"conversa": {"id": CONV["id"]}, "phone": TEL, "contact": {"name": "Ana Teste"}}])
c._estado.update(ultima=None, avisados=set())
acordou = []
c.rodada(zf, agora_c, {}, d, lambda: acordou.append(1))
g = [a for f, a in zf.env if f == "enviar_mensagem_grupo"]
assert len(g) == 1 and g[0]["grupoId"] == "claude-grupo-18" and c.TITULO in g[0]["texto"] and TEL in g[0]["texto"]
assert c.marca(img) in g[0]["texto"] and "parcela" in g[0]["texto"] and "19621586" not in g[0]["texto"] and acordou
# já avisado (marca no grupo): não repete
c._estado.update(ultima=None, avisados=set())
zf.grupo, zf.env = [{"content": g[0]["texto"]}], []
c.rodada(zf, agora_c + timedelta(minutes=6), {}, d)
assert not [f for f, a in zf.env if f == "enviar_mensagem_grupo"]
print("OK — comprovante de cliente avisado no grupo do financeiro (sem CPF/conta), uma vez só")

# ---------------------------------------------------------------- sinal da pós-reunião (só roda inteira com novidade)
import porteiro as p
gravados = []
p.gravar_no_ramo = lambda arq, conteudo, msg: gravados.append((arq, conteudo)) or True
p._pos.update(gravado_em=None, motivos=set())
agora_s = datetime(2026, 10, 27, 13, 0, tzinfo=UTC)
assert p.avisar_posreuniao("reunião concluída no EasyJur", agora_s)
assert gravados[-1][0] == "posreuniao.json" and "ultimo_evento" in gravados[-1][1] and TEL not in gravados[-1][1]
assert not p.avisar_posreuniao("arquivo novo", agora_s + timedelta(minutes=3))  # no máximo a cada 10 min
assert p.avisar_posreuniao("arquivo novo", agora_s + timedelta(minutes=11)) and "arquivo novo" in gravados[-1][1]
# no despachante: link do ZapSign e arquivo de cliente acompanhado acordam; o lembrete M1 (sem link) não
p._pos.update(gravado_em=None, motivos=set())
gravados.clear()
c._estado.update(ultima=None, avisados=set(), plantao=agora_s - timedelta(hours=1), pos_vistos=set())
lembrete_m1 = m("AGENT", "*Annie*:\nPassando para lembrar do contrato que a Dra. Fernanda te enviou pelo ZapSign.",
                agora_s - timedelta(minutes=5))
zs = Z({TEL: (CONV, [lembrete_m1])}, lista=[{"conversa": {"id": CONV["id"]}, "phone": TEL, "contact": {"name": "Ana"}}])
c.rodada(zs, agora_s, {}, d)
assert not gravados
link = m("USER", "*Dra. Fernanda Mesquita*:\nSegue o contrato: https://app.zapsign.com.br/verificar/abc", agora_s - timedelta(minutes=2))
zs.conversas = {TEL: (CONV, [lembrete_m1, link])}
c._estado["ultima"] = None
c.rodada(zs, agora_s + timedelta(minutes=6), {}, d)
assert gravados and "contrato" in gravados[-1][1]
print("OK — sinal da pós-reunião: contrato, arquivo e reunião concluída (sem dados de cliente)")
