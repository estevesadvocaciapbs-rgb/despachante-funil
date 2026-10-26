"""Teste do follow-up de lead parado na triagem (dados inventados; não acessa nenhum sistema)."""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("TELEFONES_EQUIPE", "5594992048054,5594991742534,5524992432455")
import despachante as d
import followup_lead as f

UTC = timezone.utc
CHEGOU = datetime(2026, 10, 26, 11, 46, tzinfo=UTC)  # 8h46 em Belém


def m(sender, texto, quando, nome=""):
    return {"sender": sender, "senderName": nome, "content": texto, "createdAt": quando.strftime("%Y-%m-%dT%H:%M:%S.000Z")}


lead = [m("CONTACT", "Olá! Quero sair do meu emprego e receber todos os meus benefícios", CHEGOU),
        m("AGENT", "*Annie*:\nBom dia, Edson! Eu sou a Annie, do escritório.", CHEGOU + timedelta(minutes=1)),
        m("AGENT", "*Annie*:\nPra eu te direcionar do jeito certo, me conta com calma o que está acontecendo no seu "
                   "trabalho? Pode escrever ou mandar um áudio.", CHEGOU + timedelta(minutes=1, seconds=2))]

assert f.proximo(lead, CHEGOU + timedelta(minutes=30), d)[1] > CHEGOU + timedelta(minutes=30)  # espera 1 hora
n, quando = f.proximo(lead, CHEGOU + timedelta(hours=2), d)
assert n == 1 and quando <= CHEGOU + timedelta(hours=2)
f1 = m("AGENT", "*Annie*:\n" + f.texto_followup(1, "Edson", d), CHEGOU + timedelta(hours=1, minutes=2))
assert "?" in f1["content"] and "Edson" in f1["content"]
n, quando = f.proximo(lead + [f1], CHEGOU + timedelta(hours=5), d)
assert n == 2 and quando > CHEGOU + timedelta(hours=5)  # F2 só no dia seguinte
assert f.proximo(lead + [f1], CHEGOU + timedelta(hours=22), d)[0] == 2
f2 = m("AGENT", "*Annie*:\n" + f.texto_followup(2, "Edson", d), CHEGOU + timedelta(hours=22))
n, quando = f.proximo(lead + [f1, f2], CHEGOU + timedelta(days=2), d)
assert n == 3 and quando > CHEGOU + timedelta(days=2)
f3 = m("AGENT", "*Annie*:\n" + f.texto_followup(3, "Edson", d), CHEGOU + timedelta(days=4))
assert f.proximo(lead + [f1, f2, f3], CHEGOU + timedelta(days=10), d) == (None, "fim")
# lead respondeu: a Annie continua (nada a fazer)
assert f.proximo(lead + [m("CONTACT", "trabalho sem carteira", CHEGOU + timedelta(hours=1))], CHEGOU + timedelta(hours=3), d)[0] is None
# lead respondeu ao F1 e a Annie fez outra pergunta: o ciclo recomeça a partir da nova pergunta
volta = lead + [f1, m("CONTACT", "oi, estou sim", CHEGOU + timedelta(hours=2)),
                m("AGENT", "*Annie*:\nE quanto tempo você trabalha lá?", CHEGOU + timedelta(hours=2, minutes=1))]
assert f.proximo(volta, CHEGOU + timedelta(hours=3, minutes=5), d)[0] == 1
# equipe atendendo, oferta já feita, Annie sem pergunta, pergunta antiga: não chama
for msgs in (lead + [m("USER", "*Thalyta*:\nOi, Edson!", CHEGOU + timedelta(minutes=5), "Thalyta Pereira Freitas")],
             lead + [m("AGENT", "*Annie*:\nOlá, Edson! " + d.MARCA_OFERTA + ":\n\n• terça, 27/10 às 09:30\n\nQual?",
                       CHEGOU + timedelta(minutes=5))],
             lead[:2]):
    assert f.proximo(msgs, CHEGOU + timedelta(hours=3), d)[0] is None, msgs[-1]["content"]
assert f.proximo(lead, CHEGOU + timedelta(days=4), d) == (None, "pergunta antiga demais")


class Z:
    def __init__(s, lista, conversas):
        s.env, s.lista, s.conversas = [], lista, conversas

    def chamar(s, fn, **a):
        s.env.append((fn, a))
        if fn == "listar_conversas":
            return {"atendimentos": s.lista}
        if fn == "ler_conversa":
            return {"messages": s.conversas[a["conversaId"]]}
        return {}


at = {"phone": "5542900000001", "contact": {"id": "c1", "name": "Edson"},
      "conversa": {"id": "v1", "status": "OPEN", "createdAt": "2026-10-26T11:46:25.000Z",
                   "lastMessageAt": "2026-10-26T11:47:16.000Z"}}
antigo = dict(at, phone="5542900000002", contact={"id": "c2", "name": "Cliente antigo"},
              conversa=dict(at["conversa"], id="v2", createdAt="2026-06-01T10:00:00.000Z"))
z = Z([at, antigo], {"v1": lead, "v2": lead})
f._estado["ultima"] = None
f.rodada(z, CHEGOU + timedelta(hours=3), {}, d)
env = [a for fn, a in z.env if fn == "agendar_mensagem"]
assert len(env) == 1 and env[0]["contatoId"] == "c1" and f.MARCAS[0] in env[0]["mensagem"]
assert env[0]["ativarIaAoResponder"] is True and env[0]["assinatura"] == "ia"
assert not [a for fn, a in z.env if fn == "ler_conversa" and a["conversaId"] == "v2"]  # conversa antiga nem é lida
f._estado["ultima"] = None
z = Z([at], {"v1": lead})
f.rodada(z, datetime(2026, 10, 26, 23, 30, tzinfo=UTC), {}, d)  # 20h30 em Belém: não manda
assert not [a for fn, a in z.env if fn == "agendar_mensagem"]
assert not d.precisa_retomar(lead + [f1], CHEGOU + timedelta(hours=1, minutes=4))  # o F1 tem pergunta: sem retomada
print("OK — follow-up de lead parado na triagem (1 h, dia seguinte, 3 dias)")
