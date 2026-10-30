"""Teste do aviso de lead em dúvida, com dados inventados (não acessa nenhum sistema)."""
from datetime import datetime, timedelta, timezone

import despachante as d
import followup_lead as f
import hesitacao as h

AGORA = datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)
TEL = "5571000000001"


def iso(minutos):
    return (AGORA - timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def msg(i, sender, texto, minutos):
    return {"id": f"m{i}", "sender": sender, "contentType": "CHAT", "content": texto, "createdAt": iso(minutos)}


class Z:
    def __init__(self, msgs, grupo=()):
        self.msgs, self.grupo, self.env, self.leituras = msgs, list(grupo), [], 0

    def chamar(self, f, **a):
        if f == "listar_conversas":
            return {"atendimentos": [{"phone": TEL, "lastMessageAt": iso(1), "contact": {"name": "Fulana"}, "conversa": {
                "id": "c1", "status": "OPEN", "createdAt": iso(2000), "lastMessageAt": iso(1500)}}]}
        if f == "ler_conversa":
            self.leituras += 1
            return {"messages": self.msgs}
        if f == "ler_grupo":
            return {"mensagens": self.grupo}
        self.env.append(a)


def rodar(z):
    h._estado["ultima"] = None
    h._avisados.clear()
    h._vistos.clear()
    h.rodada(z, AGORA, {}, d)


d.DRY_RUN = False
d.EQUIPE = set()
# motivos
assert h.motivo("Vou na defensoria pública", d).startswith("desistência")
assert h.motivo("É de Goiânia", d) == "distância ou outra cidade"
assert h.motivo("Moro em Parauapebas", d) is None
assert h.motivo("queria falar pessoalmente", d) == "quer atendimento presencial"
assert h.motivo("Não tenho dinheiro agora", d) == "valor ou pagamento"
assert h.motivo("vou pensar", d) == "indecisão"
assert h.motivo("Bom dia, tudo bem", d) is None
print("OK — motivos de hesitação")

# caso prioritário + recusa: avisa no grupo, uma vez
CASO = "Bati a perna no trabalho e fiquei internada."
base = [msg(1, "AGENT", "*Annie*:\nÉ assédio, gravidez, acidente ou outra coisa?", 300), msg(2, "CONTACT", CASO, 290)]
z = Z(base + [msg(3, "CONTACT", "Vou na defensoria pública", 5)])
rodar(z)
assert len(z.env) == 1 and z.env[0]["grupoId"] == d.GRUPO and z.env[0]["assinatura"] == "ia"
t = z.env[0]["texto"]
assert "🚨 *LEAD EM DÚVIDA — Fulana (5571000000001)*" in t and "acidente de trabalho" in t and "defensoria" in t
print("OK — lead prioritário hesitando avisa o grupo")

# não avisa: tema só na pergunta da Annie, frase antiga, humano já respondeu, já avisado
z = Z(base[:1] + [msg(3, "CONTACT", "vou pensar", 5)])
rodar(z)
assert not z.env
z = Z(base + [msg(3, "CONTACT", "vou pensar", 60)])
rodar(z)
assert not z.env
z = Z(base + [msg(3, "CONTACT", "vou pensar", 5), msg(4, "USER", "*Dra. Fernanda Mesquita*:\nOlá!", 2)])
rodar(z)
assert not z.env
z = Z(base + [msg(3, "CONTACT", "vou pensar", 5)], grupo=[{"content": f"🚨 *LEAD EM DÚVIDA — Fulana ({TEL})*"}])
rodar(z)
assert not z.env
print("OK — sem aviso sem tema, frase antiga, humano atendendo ou já avisado")

# follow-up para depois de recusa; continua para lead que só sumiu
com_recusa = base + [msg(3, "CONTACT", "Vou na defensoria pública", 300), msg(5, "AGENT", "*Annie*:\nTem a carta?", 290)]
assert f.proximo(com_recusa, AGORA, d)[0] is None and f.proximo(com_recusa, AGORA, d)[1] == "lead recusou"
sumiu = base + [msg(5, "AGENT", "*Annie*:\nTem a carta?", 280)]
assert f.proximo(sumiu, AGORA, d)[0] == 1
print("OK — follow-up para depois de recusa")
