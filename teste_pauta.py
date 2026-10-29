"""Teste da pauta da reunião de sexta, com dados inventados (não acessa nenhum sistema)."""
from datetime import datetime, timezone

import pauta as p
import porteiro

Q17 = datetime(2026, 11, 5, 20, 5, tzinfo=timezone.utc)   # quinta 05/11, 17h05 em Belém
S8 = datetime(2026, 11, 6, 11, 10, tzinfo=timezone.utc)   # sexta 06/11, 8h10 em Belém
FERN, LUCAS = p.ADVS[0], p.ADVS[2]


class Z:
    def __init__(self):
        self.env = []

    def chamar(self, f, **a):
        self.env.append((a["numero"], a["texto"]))


class EJ:
    def __init__(self):
        self.agenda, self.chamadas = [], []

    def chamar(self, f, **a):
        self.chamadas.append(f)
        if f == "list_agenda":
            return {"data": [dict(x) for x in self.agenda]}
        if f == "create_agenda":
            self.agenda.append({**a, "id": 77, "status": "A", "hora_inicio": a["hora_inicio"] + ":00"})
            return {"data": {"id": 77}}
        if f == "update_agenda":
            self.agenda[0]["descricao"] = a["descricao"]


def msg(i, sender, texto, quando):
    return {"id": f"claude-mensagem-{i}", "sender": sender, "contentType": "CHAT", "content": texto,
            "createdAt": quando}


# ---- leitura das respostas
assert p.ler_resposta("PAUTA\n- Conferir cálculo do caso Fulano\n2) Escala de novembro\nHORÁRIO 9h30") == \
    (["Conferir cálculo do caso Fulano", "Escala de novembro"], "9h30")
assert p.ler_resposta("pauta: honorários do caso X") == (["honorários do caso X"], None)
assert p.ler_resposta("PAUTA nada") == ([], None)
assert p.ler_resposta("Horário: 11h") == ([], "11h")
assert p.ler_resposta("pautado para amanhã") is None and p.ler_resposta("ok") is None
assert porteiro.resolvido_pelo_codigo("PAUTA\n- assunto", "fernanda")
print("OK — respostas PAUTA/HORÁRIO e porteiro")

# ---- fora da janela: nada
z, ej = Z(), EJ()
p.rodada(z, lambda: ej, {}, datetime(2026, 11, 4, 20, 5, tzinfo=timezone.utc))
assert not z.env and not ej.chamadas

# ---- quinta 17h: cria a reunião e pede a pauta aos três, uma vez só
p._estado.clear()
p.rodada(z, lambda: ej, {}, Q17)
assert ej.chamadas.count("create_agenda") == 1 and len(z.env) == 3
r = ej.agenda[0]
assert r["data"] == "2026-11-06" and r["hora_inicio"] == "10:00:00" and r["tipo"] == "REUNIAO"
assert "*Pauta da reunião de sexta, 06/11*" in z.env[0][1]
n = len(ej.chamadas)
p.rodada(z, lambda: ej, {}, Q17)
p._estado.clear()  # plantão reiniciado: a reunião já existe no EasyJur, não cria nem pede de novo
p.rodada(z, lambda: ej, {}, Q17)
assert ej.chamadas.count("create_agenda") == 1 and len(z.env) == 3 and len(ej.chamadas) == n + 1
print("OK — quinta 17h: reunião criada e pedido enviado uma vez")

# ---- resposta da Dra. Fernanda entra na descrição e recebe ✅ (uma vez)
conv = [msg(1, "AGENT", z.env[0][1], "2026-11-05T20:05:30.000Z"),
        msg(2, "CONTACT", "PAUTA\n- Conferir cálculo do caso Fulano\nHORÁRIO 9h30", "2026-11-05T21:00:00.000Z")]
p.rodada(z, lambda: ej, {FERN["tel"]: conv}, Q17)
assert "Dra. Fernanda:\n- Conferir cálculo do caso Fulano\n⏰ Dra. Fernanda sugere 9h30" in ej.agenda[0]["descricao"]
assert z.env[-1][0] == FERN["tel"] and "✅ Pauta anotada" in z.env[-1][1] and "#2" in z.env[-1][1]
conv.append(msg(3, "AGENT", z.env[-1][1], "2026-11-05T21:01:00.000Z"))
antes = len(z.env)
p.rodada(z, lambda: ej, {FERN["tel"]: conv}, Q17)
assert len(z.env) == antes and ej.agenda[0]["descricao"].count("Conferir cálculo") == 1
print("OK — PAUTA anotada no EasyJur com ✅, sem repetir")

# ---- sexta 8h: pauta consolidada aos três, uma vez
p.rodada(z, lambda: ej, {}, S8)
fim = z.env[antes:]
assert len(fim) == 3 and "*Pauta da reunião de hoje, 06/11, 10h*" in fim[0][1] and "Conferir cálculo" in fim[0][1]
assert p.ENVIADA in ej.agenda[0]["descricao"]
p._estado.clear()
p.rodada(z, lambda: ej, {}, S8)
assert len(z.env) == antes + 3
print("OK — sexta 8h: pauta enviada aos três uma vez")
