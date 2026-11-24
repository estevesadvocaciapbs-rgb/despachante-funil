"""Testes do vigia de reunião (24/11): lembrete de reunião desmarcada, remarcada ou cancelada pelo cliente sai da fila.
Dados fictícios. Rodar: python teste_vigia_reuniao.py"""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("ZAIA_TOKEN", "x")
os.environ.setdefault("EASYJUR_TOKEN", "x")
import despachante as d  # noqa: E402
import followup_lead  # noqa: E402
import resgate  # noqa: E402
import vigia_reuniao as v  # noqa: E402

BRT = d.BRT
TEL = "5591900000001"
AGORA = datetime(2026, 11, 24, 9, 0, tzinfo=BRT)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def pend(i, txt, sai, tel=TEL, contato="claude-contato-1"):
    return {"id": f"claude-agendamento-{i}", "contactId": contato, "content": txt, "scheduledAt": iso(sai),
            "status": "PENDING", "contact": {"id": contato, "name": "Fulana Teste", "phone": tel}}


class Zaia:
    def __init__(self):
        self.env = []

    def chamar(self, f, **k):
        self.env.append((f, k))
        return {}


class EJ:
    def __init__(self, itens):
        self.itens, self.env = itens, []

    def chamar(self, f, **k):
        self.env.append((f, k))
        return {"data": self.itens, "meta": {"total_pages": 1}}


class Conversas:
    def __init__(self, msgs):
        self.msgs = msgs

    def de(self, tel):
        return {"id": "c1", "contact": {"id": "claude-contato-1"}}, self.msgs


def item(status, data="2026-11-25", hora="14:30", tel=TEL, nome="Fulana Teste"):
    return {"id": 1, "tipo": "ATENDIMENTO", "status": status, "data": data, "hora_inicio": hora,
            "nome_cliente": nome, "descricao": f"Reunião com lead — {nome} ({tel}). Agendada automaticamente."}


manha = datetime(2026, 11, 25, 8, 0, tzinfo=BRT)
L8 = pend(1, "Bom dia, Fulana! Passando para lembrar do seu atendimento de hoje, às 14h30, com a Dra. Danielle "
             "Esteves, por videochamada.", manha)
L1 = pend(2, "Olá, Fulana! Passando para confirmar nosso atendimento de hoje às 14h30 com a Dra. Danielle Esteves. "
             "Podemos confirmar sua presença?", manha.replace(hour=13, minute=30))
CONF = pend(3, "Olá, Fulana! Sua reunião com a Dra. Danielle Esteves está confirmada para quarta-feira, 25/11, às "
               "14h30, por videochamada.", AGORA + timedelta(minutes=2))
OUTRA = pend(4, "Oi, Fulana! Ainda está por aí?", AGORA + timedelta(hours=1))
SLOT = datetime(2026, 11, 25, 14, 30, tzinfo=BRT)

# leitura do horário nos três formatos; mensagem que não é de reunião fica de fora
assert v.slot_do_lembrete(L8, d) == SLOT and v.slot_do_lembrete(L1, d) == SLOT and v.slot_do_lembrete(CONF, d) == SLOT
assert v.slot_do_lembrete(OUTRA, d) is None
assert set(v.lembretes_pendentes([L8, L1, CONF, OUTRA], d)) == {(TEL, SLOT)}


def rodar(itens, msgs=()):
    v._estado.update(ultima=None, avisados=set())
    z, ej = Zaia(), EJ(itens)
    ps = [dict(p) for p in (L8, L1, CONF, OUTRA)]
    v.rodada(z, lambda: ej, Conversas(list(msgs)), ps, AGORA.astimezone(timezone.utc), {}, d)
    return [k["agendamentoId"] for f, k in z.env if f == "cancelar_agendamento"], z


# 1. reunião viva: nada é cancelado
canc, z = rodar([item("A")])
assert canc == [] and not z.env, z.env
# 2. cancelada no EasyJur: os 3 de reunião saem; o follow-up comum fica; a equipe é avisada
canc, z = rodar([item("S")])
assert sorted(canc) == ["claude-agendamento-1", "claude-agendamento-2", "claude-agendamento-3"], canc
assert any(f == "enviar_mensagem_grupo" and "cancelada no EasyJur" in k["texto"] for f, k in z.env)
# 3. duplicata cancelada + original viva no mesmo horário (caso 22/11): mantém
canc, _ = rodar([item("S"), item("A")])
assert canc == []
# 4. remarcada: nada no horário antigo, outra reunião viva em outra data
canc, z = rodar([item("N", data="2026-11-27", hora="10:00")])
assert len(canc) == 3 and any("remarcada para" in k.get("texto", "") for f, k in z.env)
# 5. atendimento não achado no EasyJur: na dúvida, mantém
canc, _ = rodar([item("S", tel="5591900000009", nome="Outra Pessoa")])
assert canc == []
# 6. cliente desmarcou na conversa depois da confirmação
conf_msg = {"sender": "AGENT", "content": "*Annie*: Seu atendimento ficou marcado para quarta-feira, 25/11, às 14h30.",
            "createdAt": iso(AGORA - timedelta(hours=20))}
desmarca = {"sender": "CONTACT", "content": "Boa noite, não vou poder amanhã, surgiu um imprevisto",
            "createdAt": iso(AGORA - timedelta(hours=2))}
canc, z = rodar([item("A")], [conf_msg, desmarca])
assert len(canc) == 3 and any("marque Cancelado" in k.get("texto", "") for f, k in z.env)
# 6b. problema técnico ("não consigo entrar no link") não desmarca; quem volta atrás ("vou sim") também não
tecnico = dict(desmarca, content="não vou conseguir entrar pelo link, me ajuda?")
assert rodar([item("A")], [conf_msg, tecnico])[0] == []
volta = {"sender": "CONTACT", "content": "esquece, vou sim", "createdAt": iso(AGORA - timedelta(hours=1))}
assert rodar([item("A")], [conf_msg, desmarca, volta])[0] == []
# 6c. desmarque ANTES da confirmação (pedindo outro horário na oferta) não conta
antes = dict(desmarca, createdAt=iso(AGORA - timedelta(hours=30)))
assert rodar([item("A")], [antes, conf_msg])[0] == []
# 7. de madrugada não roda
v._estado.update(ultima=None)
z = Zaia()
v.rodada(z, lambda: EJ([item("S")]), Conversas([]), [dict(L8)], datetime(2026, 11, 24, 3, 0, tzinfo=BRT), {}, d)
assert not z.env

# trocar_lembretes: remarcação cancela o lembrete da data antiga e libera os da data nova
z = Zaia()
assert v.trocar_lembretes(z, [dict(L8), dict(L1)], "claude-contato-1", SLOT + timedelta(days=2), d) is False
assert len([1 for f, k in z.env if f == "cancelar_agendamento"]) == 2
z = Zaia()
assert v.trocar_lembretes(z, [dict(L8), dict(OUTRA)], "claude-contato-1", SLOT, d) is True and not z.env

# todos_pendentes pagina
class ZPag:
    def __init__(self):
        self.n = 0

    def chamar(self, f, **k):
        self.n += 1
        if k.get("offset", 0) == 0:
            return {"agendamentos": [1] * 100, "temMais": True, "proximoOffset": 100}
        return {"agendamentos": [2] * 7, "temMais": False, "proximoOffset": None}


assert len(v.todos_pendentes(ZPag())) == 107

# ja_na_agenda: acha a reunião de outro advogado e a cancelada
ej = EJ([dict(item("S"), id_advogado=d.LUCAS["id"])])
assert d.ja_na_agenda(ej, TEL, "Fulana Teste", SLOT)
assert not d.ja_na_agenda(EJ([item("A", hora="15:00")]), TEL, "Fulana Teste", SLOT)

# e_confirmacao: a Annie avisando que cancelou não é confirmação
of = {("25", "11", "14", "30")}
assert d.e_confirmacao("*Annie*: Prontinho, ficou marcado para quarta-feira, 25/11, às 14h30!", of)
assert not d.e_confirmacao("*Annie*: Cancelei o seu horário de 25/11, às 14h30, como pediu.", of)

# resgate: o advogado é o que o cliente ouviu no lembrete, não o 1º responsável do EasyJur
msgs = [{"sender": "AGENT", "content": L1["content"], "createdAt": iso(SLOT - timedelta(hours=1))}]
assert resgate.advogado_combinado(d, msgs, SLOT) is d.DANIELLE
assert resgate.advogado_combinado(d, [], SLOT) is None

# follow-up: no máximo 3 por semana
base = AGORA - timedelta(days=2)
fu = []
for i in range(3):
    fu += [{"sender": "AGENT", "content": "*Annie*: Qual é a sua função?", "createdAt": iso(base + timedelta(hours=i * 10))},
           {"sender": "AGENT", "content": "Oi! Ainda está por aí?", "createdAt": iso(base + timedelta(hours=i * 10 + 1))},
           {"sender": "CONTACT", "content": "oi", "createdAt": iso(base + timedelta(hours=i * 10 + 2))}]
fu.append({"sender": "AGENT", "content": "*Annie*: E o seu salário?", "createdAt": iso(AGORA - timedelta(hours=3))})
assert followup_lead.proximo(fu, AGORA, d) == (None, "limite semanal de follow-ups")
print("ok — vigia de reunião, agenda sem duplicar, confirmação, resgate e follow-up")
