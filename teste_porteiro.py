"""Teste do porteiro com dados inventados (não chama o GitHub nem a Za.Ia de verdade)."""
from datetime import datetime, timedelta, timezone
import porteiro as p

INICIO = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
chamadas = []
p.chamar_claude = lambda: chamadas.append(1) or True
fin = []
p.avisar_financeiro = lambda: fin.append(1) or True


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
    p._estado.update(ultima=None, desde=None, visto={}, chamado_em=None, pendente=False,
                     fin_chamado_em=None, fin_pendente=False)
    chamadas.clear()
    fin.clear()


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

# ---- despesas/repasses aprovados ainda não lançados (lista só de códigos, para o lançamento noturno)
from datetime import datetime as _dt, timezone as _tz
_ag = _dt(2026, 10, 19, 23, 0, tzinfo=_tz.utc)
_msgs = [
    {"createdAt": "2026-10-19T20:00:00.000Z", "content": "💸 *REPASSE/DESPESA F7 (manual)* — Pedido de: Dra. Fernanda."},
    {"createdAt": "2026-10-19T20:10:00.000Z", "content": "OK F7"},
    {"createdAt": "2026-10-19T20:50:00.000Z", "content": "✅ F7 repasse aprovado por Dr. Lucas — entra no lançamento das 22h"},
    {"createdAt": "2026-10-19T21:50:00.000Z", "content": "✅ *F8* despesa aprovada por Dra. Danielle"},
    {"createdAt": "2026-10-19T22:00:00.000Z", "content": "✅ F4 lançado no EasyJur — receita nº 1"},
    {"createdAt": "2026-10-10T20:50:00.000Z", "content": "✅ F2 despesa aprovada por Dr. Lucas"},
]
assert p.despesas_pendentes(_msgs, _ag) == ["F7 de 19/10", "F8 de 19/10"], p.despesas_pendentes(_msgs, _ag)
_msgs.append({"createdAt": "2026-10-20T01:05:00.000Z", "content": "🧾 F7 de 19/10 lançada no EasyJur — despesa nº 99"})
assert p.despesas_pendentes(_msgs, _ag) == ["F8 de 19/10"]
print("OK — despesas aprovadas a lançar")

# ---- verbos de pedido no grupo (caso real de 20/10: "Insira na minha agenda" ficou 37 min sem resposta)
for _t, _esp in [("Insira na minha agenda , em tarefas , para eu analisar\nA documentação , hoje as 15:30 .", True),
                 ("Bom dia, inclua na minha agenda amanhã", True), ("Por favor , desenhe", True),
                 ("Lucas pode deixar que quando for assim ela faz", False), ("Show", False), ("Entendi", False),
                 ("A procuração é da representante da filha do Alan.", False)]:
    assert bool(p.RE_PEDIDO_GRUPO.search(p.norm(_t))) == _esp, _t
print("OK — verbos de pedido no grupo (insira, inclua, depois de cumprimento)")

# CLIENTE é executado pela secretaria sem IA: não acorda o Claude (nem com o texto em várias linhas)
assert p.resolvido_pelo_codigo("CLIENTE 1 A2", "fernanda")
assert p.resolvido_pelo_codigo("CLIENTE 2: Olá, Maria!\nSaiu a sentença.", "danielle")
assert p.resolvido_pelo_codigo("CLIENTE T1", "lucas")
# no privado do Dr. Lucas, AGENDAR não é da secretaria: tem de acordar o Claude
assert not p.resolvido_pelo_codigo("Agende reunião com a Maria dia 22/10 às 14h", "lucas")
assert p.resolvido_pelo_codigo("Agende reunião com a Maria dia 22/10 às 14h", "fernanda")
print("OK — porteiro x CLIENTE")

# grupo "Financeiro Escritório": mensagem de advogado acorda só o financeiro (não o Secretário/Respostas)
novo_plantao()
z = FakeZ(grupos={"claude-grupo-18": []})
p.rodada(z, INICIO)
z.grupos["claude-grupo-18"] = [m("CONTACT", "Rebeca pagou 500 de entrada hoje", 1, "Fernanda Mesquita"),
                               m("USER", "oi", 1)]
p.rodada(z, INICIO + timedelta(minutes=2))
assert fin == [1] and not chamadas
p.rodada(z, INICIO + timedelta(minutes=4))
assert fin == [1]  # a mesma mensagem não chama de novo
z.grupos["claude-grupo-18"].append(m("USER", "💰 *LANÇAMENTO F3*", 5))  # mensagem do sistema não chama
p.rodada(z, INICIO + timedelta(minutes=12))
assert fin == [1]
z.grupos["claude-grupo-18"].append(m("CONTACT", "ok f3", 13, "Lucas Seoane"))
p.rodada(z, INICIO + timedelta(minutes=14))
assert fin == [1, 1] and not chamadas
print("OK — grupo do financeiro acorda só a rotina financeira")

# Aviso da manhã no grupo do financeiro (caso real de 21-22/10/2026: F4 esperando forma, F5/F6 aprovadas sem 🧾)
from datetime import datetime as _dt
def mg(sender, texto, iso, nome=None):
    return {"sender": sender, "senderName": nome, "content": texto, "createdAt": iso}
GRUPO18 = [
    mg("CONTACT", "Dar baixa no pagamento (DESPESA) para CODELAW Laura, R$ 1.250,00 em 21/10/2026", "2026-10-22T00:13:20.000Z", "Danielle Esteves"),
    mg("AGENT", "*Annie*:\n💸 *DESPESA F4* — Pedido de: Dra. Danielle (grupo Financeiro)\nTipo: Despesa do escritório\n"
       "Favorecido: CODELAW Laura\nValor: R$ 1.250,00 · PAGO em 21/10 · forma ⟨ ⟩ · banco NUBANK\n"
       "⚠️ falta forma de pagamento (a imagem enviada em grupo não é lida): use EDITAR F4: Pix\n👉 Confirme: *OK F4*", "2026-10-22T00:21:36.971Z"),
    mg("AGENT", "*Annie*:\n💸 *DESPESA F5* — Pedido de: Dr. Lucas (privado)\nFavorecido: Dr. Lucas Seoane\nValor: R$ 225,00 · forma ⟨ ⟩", "2026-10-22T00:52:04.000Z"),
    mg("CONTACT", "Editar f5: 3 parcelas pagas, no pix", "2026-10-22T01:02:28.000Z", "Lucas Seoane"),
    mg("AGENT", "*Annie*:\n✅ F5 despesa aprovada por Dr. Lucas (EDITAR) — entra no lançamento das 22h.\nDados finais: Tipo: Repasse · "
       "Favorecido: Dr. Lucas Seoane\n\n💸 *DESPESA F6* — Pedido de: Dr. Lucas (privado)\nFavorecido: Dr. Lucas Seoane\nValor: R$ 350,00 · forma ⟨ ⟩",
       "2026-10-22T01:21:48.000Z"),
    mg("CONTACT", "Editar f6: pago em 15/09, pix", "2026-10-22T01:45:19.000Z", "Lucas Seoane"),
    mg("AGENT", "*Annie*:\n✅ F6 despesa aprovada por Dr. Lucas (EDITAR) — entra no lançamento das 22h.\nDados finais: Favorecido: Dr. Lucas Seoane\n\n"
       "💰 *BAIXA F7* — Pedido de: Dr. Lucas\nreceita nº 5217483\n👉 *OK F7*", "2026-10-22T01:51:38.000Z"),
    mg("CONTACT", "Ok F7", "2026-10-22T02:20:15.000Z", "Lucas Seoane"),
    mg("AGENT", "*Annie*:\n✅ F7 baixa feita — receita nº 5217483", "2026-10-22T02:22:50.000Z"),
]
manha = _dt(2026, 10, 22, 11, 5, tzinfo=timezone.utc)  # 08:05 em Belém
itens = dict(p.pendencias_financeiro(GRUPO18, manha))
assert set(itens) == {"F4 de 21/10", "F5 de 21/10", "F6 de 21/10"}, itens
assert "esperando dado (falta forma de pagamento)" in itens["F4 de 21/10"] and "CODELAW Laura" in itens["F4 de 21/10"]
assert "entra no lançamento de hoje às 22h" in itens["F5 de 21/10"]  # aprovada depois das 22h de ontem
assert "Dr. Lucas Seoane" in itens["F6 de 21/10"]  # favorecido no meio da linha dos "Dados finais"
# no dia seguinte, sem 🧾, vira alerta de atraso
amanha = dict(p.pendencias_financeiro(GRUPO18, _dt(2026, 10, 23, 11, 5, tzinfo=timezone.utc)))
assert "já devia ter entrado" in amanha["F5 de 21/10"]
# 🧾 e EDITAR do advogado tiram da lista
resolvido = GRUPO18 + [mg("AGENT", "*Annie*:\n🧾 F4 de 21/10 lançada no EasyJur\n🧾 F5 de 21/10 — já existia\n🧾 F6 de 21/10 — idem",
                          "2026-10-22T13:00:00.000Z")]
assert p.pendencias_financeiro(resolvido, _dt(2026, 10, 22, 15, 0, tzinfo=timezone.utc)) == []
assert "F4 de 21/10" not in dict(p.pendencias_financeiro(GRUPO18 + [mg("CONTACT", "EDITAR F4: Pix", "2026-10-22T10:00:00.000Z", "Danielle Esteves")], manha))

class FakeZEnvio(FakeZ):
    def __init__(self, grupos):
        super().__init__(grupos=grupos)
        self.enviadas = []
    def chamar(self, f, **a):
        if f == "enviar_mensagem_grupo":
            assert a["assinatura"] == "ia" and a["grupoId"] == "claude-grupo-18"
            self.enviadas.append(a["texto"])
            self.grupos["claude-grupo-18"].append(mg("AGENT", "*Annie*:\n" + a["texto"], "2026-10-22T11:06:00.000Z"))
            return {}
        return super().chamar(f, **a)

novo_plantao(); p._estado["aviso_fin"] = None
z = FakeZEnvio({"claude-grupo-18": list(GRUPO18)})
p.avisar_pendencias(z, z.grupos["claude-grupo-18"], _dt(2026, 10, 22, 10, 30, tzinfo=timezone.utc))  # 07:30: cedo
assert not z.enviadas
p.avisar_pendencias(z, z.grupos["claude-grupo-18"], manha)
assert len(z.enviadas) == 1 and z.enviadas[0].startswith("⏰ *Pendências do financeiro — 22/10*")
assert "🧾 F" not in z.enviadas[0].split("\n_")[0] and not p.RE_DESP_APROVADA.search(z.enviadas[0])  # não confunde a fila
p._estado["aviso_fin"] = None  # outro plantão no mesmo dia: acha o aviso no grupo e não repete
p.avisar_pendencias(z, z.grupos["claude-grupo-18"], manha.replace(hour=13))
assert len(z.enviadas) == 1
p._estado["aviso_fin"] = None
p.avisar_pendencias(z, z.grupos["claude-grupo-18"], _dt(2026, 10, 24, 11, 5, tzinfo=timezone.utc))  # sábado
assert len(z.enviadas) == 1
print("OK — aviso da manhã: aprovado sem 🧾 e rascunho parado, uma vez por dia útil")
