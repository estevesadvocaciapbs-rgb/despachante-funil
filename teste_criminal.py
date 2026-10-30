"""Teste do aviso de caso criminal à Dra. Fernanda, com dados inventados (não acessa nenhum sistema)."""
import despachante as d


class Z:
    def __init__(self):
        self.env = []

    def chamar(self, f, **a):
        self.env.append(a)


class Conv:
    def __init__(self, msgs=()):
        self.msgs, self.leituras = list(msgs), 0

    def de(self, tel):
        self.leituras += 1
        return {}, self.msgs


def lead(tel, texto):
    return {"tel": tel, "nome": "Fulana", "texto": texto}


AG = "‼️NOVA OPORTUNIDADE‼️\nÁREA: Família — Partilha\nFulana relata agressões do ex-companheiro."
d.DRY_RUN = False
d._criminais.clear()

# lead de Família com agressão no relato: avisa, uma vez só
z, c = Z(), Conv()
d.avisar_criminal(z, c, lead("5594000000001", AG), "familia")
d.avisar_criminal(z, c, lead("5594000000001", AG), "familia")
assert len(z.env) == 1 and c.leituras == 1
a = z.env[0]
assert a["numero"] == d.FERNANDA["tel"] and a["assinatura"] == "ia"
assert "🚨 *CASO CRIMINAL — Fulana (5594000000001)*" in a["texto"]
print("OK — agressão em lead de Família avisa a Dra. Fernanda uma vez")

# área criminal e violência doméstica avisam mesmo sem palavra-chave; trabalhista comum não
z, c = Z(), Conv()
d.avisar_criminal(z, c, lead("5594000000002", "ÁREA: Criminal"), "criminal")
d.avisar_criminal(z, c, lead("5594000000003", "sem palavra"), "vd")
d.avisar_criminal(z, c, lead("5594000000004", "ÁREA: Trabalhista\nHoras extras e FGTS atrasado."), "trabalhista")
assert [x["texto"].split("(")[1][:13] for x in z.env] == ["5594000000002", "5594000000003"]
print("OK — criminal e VD avisam; trabalhista comum não")

# plantão reiniciado: o aviso já está na conversa, não repete
d._criminais.clear()
z, c = Z(), Conv([{"content": "*Annie*:\n🚨 *CASO CRIMINAL — Fulana (5594000000001)*"}])
d.avisar_criminal(z, c, lead("5594000000001", AG), "familia")
assert not z.env
print("OK — não repete depois de reiniciar o plantão")
