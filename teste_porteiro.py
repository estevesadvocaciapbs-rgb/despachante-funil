"""Teste do porteiro com dados inventados (não chama o GitHub nem a Za.Ia de verdade)."""
from datetime import datetime, timedelta, timezone
import porteiro as p

INICIO = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
chamadas = []
p.chamar_claude = lambda: chamadas.append(1) or True


def m(sender, texto, minutos, nome=None, tipo="CHAT"):
    return {"sender": sender, "senderName": nome, "content": texto, "contentType": tipo,
            "createdAt": (INICIO + timedelta(minutes=minutos)).isoformat().replace("+00:00", "Z")}


class FakeZ:
    def __init__(self, privados=None, grupos=None):
        self.privados, self.grupos = privados or {}, grupos or {}

    def chamar(self, f, **a):
        if f == "buscar_conversa_por_telefone":
            msgs = self.privados.get(a["telefone"], [])
            return {"conversa": {"id": a["telefone"], "lastMessageAt": msgs[-1]["createdAt"] if msgs else None}}
        if f == "ler_conversa":
            return {"messages": self.privados.get(a["conversaId"], [])}
        if f == "ler_grupo":
            return {"mensagens": self.grupos.get(a["grupoId"], [])}
        return {}


def novo_plantao():
    p._estado.update(ultima=None, desde=None, visto={}, chamado_em=None, pendente=False)
    chamadas.clear()


FERN = "5594991742534"

# mensagem antiga (antes do plantão) não chama
novo_plantao()
z = FakeZ({FERN: [m("CONTACT", "marca a Patrícia sexta 14h", -30)]})
p.rodada(z, INICIO)
assert not chamadas

# pedido livre no privado chama uma vez
z.privados[FERN].append(m("CONTACT", "marca a Patrícia sexta 14h", 1))
p.rodada(z, INICIO + timedelta(minutes=2))
assert len(chamadas) == 1
# a mesma mensagem não chama de novo
p.rodada(z, INICIO + timedelta(minutes=10))
assert len(chamadas) == 1
print("OK — pedido livre no privado chama o Claude uma vez")

# comando que a secretaria sem IA resolve não chama
novo_plantao()
z = FakeZ({FERN: []})
p.rodada(z, INICIO)
z.privados[FERN] = [m("CONTACT", "LIDA 1 3", 1), m("CONTACT", "minha agenda", 2)]
p.rodada(z, INICIO + timedelta(minutes=3))
assert not chamadas
# mas OK S2 (aprovação do Secretário) e comprovante chamam
z.privados[FERN].append(m("CONTACT", "Ok S2", 4))
p.rodada(z, INICIO + timedelta(minutes=6))
assert len(chamadas) == 1
print("OK — comandos de formato fixo ficam com o código")

# mensagem da própria automação (AGENT) não chama
novo_plantao()
z = FakeZ({FERN: []})
p.rodada(z, INICIO)
z.privados[FERN] = [m("AGENT", "🧭 ENTENDI S3 ...", 1)]
p.rodada(z, INICIO + timedelta(minutes=2))
assert not chamadas
print("OK — mensagem do sistema não chama")

# grupo: conversa da equipe não chama; pedido dirigido ao sistema chama
novo_plantao()
z = FakeZ(grupos={"claude-grupo-1": []})
p.rodada(z, INICIO)
z.grupos["claude-grupo-1"] = [m("CONTACT", "vou ver aqui", 1, "Fernanda Mesquita"),
                              m("CONTACT", "Agende a Ana amanhã 10h", 1, "Thalyta")]
p.rodada(z, INICIO + timedelta(minutes=2))
assert not chamadas
z.grupos["claude-grupo-1"].append(m("CONTACT", "Responda o Fulano que a audiência foi adiada", 3, "Lucas Seoane"))
p.rodada(z, INICIO + timedelta(minutes=4))
assert len(chamadas) == 1
print("OK — no grupo só pedido de advogado ao sistema chama")

# vários pedidos seguidos: espera 5 minutos entre chamadas e não perde o último
novo_plantao()
z = FakeZ({FERN: []})
p.rodada(z, INICIO)
z.privados[FERN] = [m("CONTACT", "cria tarefa pra mim amanhã", 1)]
p.rodada(z, INICIO + timedelta(minutes=2))
z.privados[FERN].append(m("CONTACT", "e anota no contato do João", 3))
p.rodada(z, INICIO + timedelta(minutes=4))
assert len(chamadas) == 1  # ainda dentro da espera
p.rodada(z, INICIO + timedelta(minutes=8))
assert len(chamadas) == 2  # o pedido que ficou pendente sai depois da espera
print("OK — espera entre chamadas sem perder pedido")
