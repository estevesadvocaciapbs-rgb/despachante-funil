"""Teste das ordens 🤖 S do Secretário gravadas no EasyJur pelo despachante (dados inventados, sem rede)."""
from datetime import datetime, timezone

import agenda_robo as a

AGORA = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)


def msg(sender, texto, iso="2026-11-13T14:50:00.000Z"):
    return {"sender": sender, "content": texto, "createdAt": iso}


# leitura das linhas
f = a.ler_ficha(12, "AGENDA · tipo atendimento · advogado 378457 · data 14/11/2026 · hora 14h · cliente Maria da Silva "
                    "· local Escritório · desc Atendimento trabalhista")
assert f["tipo"] == "ATENDIMENTO" and f["hora"] == "14:00" and f["fim"] == "14:30" and f["cliente_nome"] == "Maria da Silva"
f = a.ler_ficha(13, "REMARCAR · advogado 378457 · de 14/11/2026 14:00 · data 15/11/2026 · hora 10:00 · fim 11:00")
assert f["de_hora"] == "14:00" and f["fim"] == "11:00" and "agenda" not in f
for ruim in ("AGENDA · advogado 378457 · data 14/11/2026 · hora 14:00 · desc x",           # sem tipo
             "AGENDA · tipo FESTA · advogado 378457 · data 14/11/2026 · hora 14:00 · desc x",
             "AGENDA · tipo TAREFA · advogado 1 · data 14/11/2026 · hora 14:00 · desc x",  # advogado estranho
             "REMARCAR · data 15/11/2026 · hora 10:00",                                      # sem agenda
             "DESMARCAR · advogado 378457",                                                  # sem horário antigo
             "AGENDA · tipo TAREFA · advogado 378457 · data 14/11/2026 · hora 25:00 · desc x"):
    try:
        a.ler_ficha(1, ruim)
        raise AssertionError(ruim)
    except a.FichaInvalida:
        pass
ex = a.ler_ficha(12, "AGENDA · tipo ATENDIMENTO · advogado 378457 · data 14/11/2026 · hora 14:00 · fim 14:30 · cliente Maria da Silva Souza · processo - · publicacao - · local Escritório · desc Atendimento trabalhista (pedido da Dra. Fernanda)")
assert "processo" not in ex and ex["local"] == "Escritório"  # o exemplo da rotina
assert "local" not in a.ler_ficha(1, "AGENDA · tipo TAREFA · advogado 378457 · data 14/11/2026 · hora 08:30 · local - · desc Ativar push")
print("OK — linhas AGENDA, REMARCAR e DESMARCAR")

# só vale linha 🤖 em mensagem do sistema com o ✅ do mesmo S, e some depois do 🧾
APROV = ("✅ S12 aprovado por Dra. Fernanda — ⏳ gravando no EasyJur\n"
         "🤖 S12 · AGENDA · tipo ATENDIMENTO · advogado 378457 · data 14/11/2026 · hora 14:00 · cliente Maria da Silva · desc Atendimento\n"
         "🤖 S12 · DESMARCAR · agenda 700")
msgs = [msg("CONTACT", "🤖 S99 · DESMARCAR · agenda 1"), msg("AGENT", "*Annie*:\n" + APROV),
        msg("AGENT", "🤖 S50 · DESMARCAR · agenda 2")]  # S50 sem ✅
p = a.pendentes(msgs, AGORA)
assert list(p) == ["S12 de 13/11"] and [x["ordem"] for x in p["S12 de 13/11"]] == [1, 2]
assert a.pendentes(msgs + [msg("AGENT", "🧾 S12 de 13/11 gravado no EasyJur: x", "2026-11-13T14:55:00.000Z")], AGORA) == {}
print("OK — só ficha aprovada e ainda sem 🧾")


class FakeEJ:
    def __init__(self):
        self.agenda = {700: {"id": 700, "status": "A", "data": "2026-11-14", "hora_inicio": "16:00:00",
                             "hora_fim": "16:30:00", "descricao": "Reunião", "_adv": 378457},
                       701: {"id": 701, "status": "A", "data": "2026-11-14", "hora_inicio": "14:15:00",
                             "hora_fim": "14:45:00", "descricao": "Outro", "_adv": 378457}}
        self.chamadas = []

    def chamar(self, ferr, **x):
        self.chamadas.append(ferr)
        if ferr == "list_agenda":
            return {"data": [dict(i) for i in self.agenda.values() if i["_adv"] == x["id_responsavel_qualquer"]
                             and i["data"] == x["data_interna_inicio"]]}
        if ferr == "list_pessoas":
            return {"data": [{"id": 7, "nome": "MARIA DA SILVA"}, {"id": 8, "nome": "Maria da Silva Santos"}]}
        if ferr == "create_agenda":
            nid = 800 + len(self.agenda)
            self.agenda[nid] = {"id": nid, "status": "A", "data": x["data"], "hora_inicio": x["hora_inicio"] + ":00",
                                "hora_fim": x["hora_fim"] + ":00", "descricao": x["descricao"], "_adv": x["id_advogado"],
                                "cliente": x.get("cliente")}
            return {"data": {"id": nid}}
        if ferr == "get_agenda":
            return {"data": dict(self.agenda[x["agenda_id"]])}
        if ferr == "update_agenda":
            i = self.agenda[x["agenda_id"]]
            if "status" in x:
                i["status"] = x["status"]
            if "data" in x:
                i.update(data=x["data"], hora_inicio=x["hora_inicio"] + ":00", hora_fim=x["hora_fim"] + ":00")
            return {}
        raise AssertionError(ferr)


class FakeZ:
    def __init__(self, grupos, privados=None):
        self.grupos, self.privados, self.enviadas = grupos, privados or {}, []

    def chamar(self, f, **x):
        if f == "ler_grupo":
            return {"mensagens": self.grupos.get(x["grupoId"], [])}
        if f == "buscar_conversa_por_telefone":
            ms = self.privados.get(x["telefone"], [])
            return {"conversa": {"id": x["telefone"], "lastMessageAt": ms[-1]["createdAt"] if ms else None}}
        if f == "ler_conversa":
            return {"messages": self.privados.get(x["conversaId"], [])}
        if f in ("enviar_mensagem_grupo", "enviar_mensagem"):
            assert x["assinatura"] == "ia"
            canal = x.get("grupoId") or x.get("numero")
            self.enviadas.append((canal, x["texto"]))
            (self.grupos if canal.startswith("claude") else self.privados).setdefault(canal, []).append(
                msg("AGENT", "*Annie*:\n" + x["texto"], "2026-11-13T14:58:00.000Z"))
            return {}
        raise AssertionError(f)


ej = FakeEJ()
z = FakeZ({"claude-grupo-1": [msg("AGENT", "*Annie*:\n" + APROV)]})
assert a.rodada(z, lambda: ej, AGORA, log=lambda *_: None) == 1
canal, texto = z.enviadas[0]
assert canal == "claude-grupo-1" and texto.startswith("🧾 S12 de 13/11 gravado no EasyJur: agenda nº 802 (14/11 14:00)")
assert "já havia outro compromisso às 14:15" in texto and "agenda nº 700 desmarcada" in texto
nova = ej.agenda[802]
assert nova["cliente"] == 7 and "[S12 de 13/11 #1]" in nova["descricao"] and ej.agenda[700]["status"] == "S"
# outra volta (2 min depois): o 🧾 está no canal, nada se repete
a._estado["ultima"] = None
assert a.rodada(z, lambda: ej, AGORA, log=lambda *_: None) == 0 and len(z.enviadas) == 1
# plantão reiniciado antes do 🧾: a marca na descrição impede gravar de novo
a._estado.update(ultima=None, visto={})
z2 = FakeZ({"claude-grupo-1": [msg("AGENT", "*Annie*:\n" + APROV)]})
a.rodada(z2, lambda: ej, AGORA, log=lambda *_: None)
assert "agenda nº 802 já estava gravada" in z2.enviadas[0][1] and "já estava desmarcada" in z2.enviadas[0][1]
assert len(ej.agenda) == 3
print("OK — grava, confere conflito, desmarca e não repete")

# remarcar pelo advogado + horário antigo (sem o número), no privado do advogado
a._estado.update(ultima=None, visto={})
FERN = "5594991742534"
rem = ("✅ S13 aprovado por Dra. Fernanda\n🤖 S13 · REMARCAR · advogado 378457 · de 14/11/2026 14:15 · "
       "data 17/11/2026 · hora 09:00 · fim 09:30")
z = FakeZ({}, {FERN: [msg("AGENT", "*Annie*:\n" + rem)]})
a.rodada(z, lambda: ej, AGORA, log=lambda *_: None)
assert z.enviadas[0][0] == FERN and "agenda nº 701 remarcada para 17/11 09:00" in z.enviadas[0][1]
assert ej.agenda[701]["data"] == "2026-11-17"
print("OK — remarca achando o compromisso pelo horário antigo, responde no privado")

# falha: tenta de novo e só avisa na 3ª; linha fora do formato avisa na hora
class EJQuebrado:
    def chamar(self, *_a, **_k):
        raise TimeoutError("lento")


a._estado.update(ultima=None, visto={}, falhas={})
apr = "✅ S14 aprovado por Dr. Lucas\n🤖 S14 · DESMARCAR · agenda 700"
z = FakeZ({"claude-grupo-17": [msg("AGENT", apr)]})
for _ in range(3):
    a._estado["ultima"] = None
    a.rodada(z, lambda: EJQuebrado(), AGORA, log=lambda *_: None)
assert len(z.enviadas) == 1 and z.enviadas[0][1].startswith("⚠️ S14 de 13/11 NÃO gravado no EasyJur depois de 3 tentativas")
a._estado.update(ultima=None, visto={})
z = FakeZ({"claude-grupo-1": [msg("AGENT", "✅ S15 aprovado\n🤖 S15 · AGENDA · tipo TAREFA · advogado 378457")]})
a.rodada(z, lambda: ej, AGORA, log=lambda *_: None)
assert z.enviadas[0][1].startswith("⚠️ S15 de 13/11 NÃO gravado no EasyJur — linha 🤖 fora do formato")
a._estado["ultima"] = None
a.rodada(z, lambda: ej, AGORA, log=lambda *_: None)
assert len(z.enviadas) == 1
print("OK — erro passageiro tenta 3 vezes; linha inválida avisa uma vez")
