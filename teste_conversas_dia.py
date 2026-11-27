"""Testes offline das conversas do dia (conversas_dia.py). Só dados inventados (telefones 5500000000xxx).
Rodar: python teste_conversas_dia.py"""
import contextlib
import io
from datetime import date, datetime, timedelta, timezone

import conversas_dia as cd

UTC = timezone.utc
BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 27, 22, 0, tzinfo=UTC)  # 27/11 19h em Belém
CLIENTE, LEAD, ANTIGO = "5500000000101", "5500000000102", "5500000000103"
SEGREDO = "TEXTO-QUE-NUNCA-PODE-SAIR"


def h(dia, hh, mm=0):
    return datetime(2026, 11, dia, hh, mm, tzinfo=BRT).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def msg(sender, quando, texto=SEGREDO, nome=""):
    return {"sender": sender, "createdAt": quando, "content": texto, "senderName": nome, "contentType": "TEXT"}


# --- quem escreveu
assert cd.autor(msg("CONTACT", h(27, 9))) == "cliente"
assert cd.autor(msg("AGENT", h(27, 9))) == "Annie"
assert cd.autor(msg("USER", h(27, 9), "*Annie*:\noi", "Automação")) == "Annie"
assert cd.autor(msg("USER", h(27, 9), "*Dr. Lucas*:\noi", "Automação")) == "Dr. Lucas"
assert cd.autor(msg("USER", h(27, 9), "*Dra Danielle Esteves*:\noi")) == "Dra. Danielle Esteves"
assert cd.autor(msg("USER", h(27, 9), "*Atendente Teste:*\noi")) == "Atendente Teste"
assert cd.autor(msg("USER", h(27, 9), "oi", "")) == "equipe (sem assinatura)"

# --- contagens de um dia
conversa_cliente = [
    msg("CONTACT", h(26, 18)),                       # ontem
    msg("CONTACT", h(27, 9, 0)),
    msg("AGENT", h(27, 9, 1)),
    msg("CONTACT", h(27, 11, 30)),                   # 2h29 depois: retomada
    msg("USER", h(27, 11, 40), "*Dr. Lucas*:\n" + SEGREDO),
    msg("CONTACT", h(27, 17, 0)),                    # retomada e fica sem resposta
    msg("CONTACT", h(27, 17, 5)),
]
ini, fim = datetime(2026, 11, 27, tzinfo=BRT), AGORA
r = cd.resumo_do_dia(conversa_cliente, ini, fim)
assert r["msgs_cliente"] == 4 and r["msgs_annie"] == 1 and r["msgs_equipe"] == 1 and r["total_msgs"] == 6, r
assert r["retomadas"] == 2 and r["quem_iniciou"] == "cliente", r
assert r["primeira_msg"] == "09:00" and r["ultima_msg"] == "17:05", r
assert r["sem_resposta"] == 1 and r["minutos_sem_resposta"] == 120, r  # desde 17h00 até 19h00
assert r["quem_respondeu"] in ("Annie, Dr. Lucas", "Dr. Lucas, Annie"), r
assert cd.resumo_do_dia(conversa_cliente, datetime(2026, 11, 25, tzinfo=BRT), datetime(2026, 11, 26, tzinfo=BRT)) is None

respondida = [msg("USER", h(27, 10), "*Annie*:\nbom dia"), msg("CONTACT", h(27, 10, 5)), msg("AGENT", h(27, 10, 6))]
r = cd.resumo_do_dia(respondida, ini, fim)
assert r["sem_resposta"] == 0 and r["minutos_sem_resposta"] == 0 and r["quem_iniciou"] == "escritório", r


# --- rodada completa com Za.Ia, EasyJur e planilha falsos
def atendimento(cid, tel, nome, criada):
    return {"phone": tel, "name": nome, "contact": {"id": f"contato-{cid}", "name": nome, "phone": tel},
            "conversa": {"id": f"conversa-{cid}", "status": "OPEN", "createdAt": criada}}


EQUIPE_TEL = next(iter(cd.despachante.ADVOGADOS))["tel"]


class FakeZaia:
    def __init__(self):
        self.chamadas = []

    def chamar(self, ferr, **x):
        self.chamadas.append((ferr, x))
        if ferr == "listar_conversas":
            if x.get("status") == "CLOSED":
                return {"atendimentos": [atendimento(1, CLIENTE, "Cliente Inventado", h(1, 8))], "total": 1}
            return {"atendimentos": [atendimento(1, CLIENTE, "Cliente Inventado", h(1, 8)),
                                     atendimento(2, LEAD, "Lead Inventado", h(26, 8)),
                                     atendimento(3, ANTIGO, "Contato Antigo", "2025-01-01T12:00:00.000Z"),
                                     atendimento(4, EQUIPE_TEL, "Advogado", h(1, 8))], "total": 4}
        if ferr == "ler_conversa":
            if x["conversaId"] == "conversa-1":
                return {"messages": list(reversed(conversa_cliente))}  # a Za.Ia devolve do mais novo ao mais velho
            if x["conversaId"] == "conversa-2":
                return {"messages": [msg("CONTACT", h(27, 15)), msg("AGENT", h(27, 15, 1))]}
            if x["conversaId"] == "conversa-3":
                return {"messages": [msg("CONTACT", h(27, 8))]}
            raise AssertionError("conversa da equipe não deveria ser lida")
        if ferr == "listar_contatos":
            return {"contatos": [{"phone": ANTIGO}] if x["etiqueta"] == "Reclamada" else []}
        raise AssertionError(ferr)


class FakeEJ:
    def __init__(self):
        self.chamadas = []

    def chamar(self, ferr, **x):
        self.chamadas.append(ferr)
        if ferr == "list_processos":
            return {"data": [{"id_cliente": 900}, {"id_cliente": 900}, {"id_cliente": 901}], "meta": {"total_pages": 1}}
        if ferr == "get_pessoa":
            return {"data": {"celular": "(00) 0000-0000"}}  # inválido: fica no cache como sem celular
        raise AssertionError(ferr)


class FakePonte:
    def __init__(self):
        self.gravado, self.clientes_novos = None, None

    def __call__(self, acao, **x):
        if acao == "ler_clientes":
            return {"ok": True, "clientes": {"900": CLIENTE}}
        if acao == "gravar_clientes":
            self.clientes_novos = x["clientes"]
            return {"ok": True}
        if acao == "gravar_dia":
            self.gravado = x
            return {"ok": True, "linhas": len(x["linhas"]), "total": len(x["linhas"])}
        raise AssertionError(acao)


zaia, ej, ponte = FakeZaia(), FakeEJ(), FakePonte()
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    linhas = cd.rodada(zaia, ej, ponte=ponte, agora=AGORA)

col = cd.COLUNAS.index
assert ponte.gravado["dias"] == ["2026-11-26", "2026-11-27"], ponte.gravado["dias"]
assert ponte.gravado["colunas"] == cd.COLUNAS
assert ponte.clientes_novos == {"901": ""}, ponte.clientes_novos  # só a pessoa nova vai ao get_pessoa
assert ej.chamadas.count("get_pessoa") == 1
por_chave = {(l[col("data")], l[col("id_conversa")]): l for l in linhas}
assert set(por_chave) == {("2026-11-26", "conversa-1"), ("2026-11-27", "conversa-1"),
                          ("2026-11-27", "conversa-2"), ("2026-11-27", "conversa-3")}, set(por_chave)
c = por_chave[("2026-11-27", "conversa-1")]
assert c[col("tipo")] == "cliente ativo" and c[col("id_pessoa_easyjur")] == "900" and c[col("processos_ativos")] == 2
assert por_chave[("2026-11-27", "conversa-2")][col("tipo")] == "lead"
assert por_chave[("2026-11-27", "conversa-3")][col("tipo")] == "outro"  # etiqueta Reclamada
assert por_chave[("2026-11-27", "conversa-3")][col("sem_resposta")] == 1
assert len([f for f, x in zaia.chamadas if f == "ler_conversa"]) == 3  # uma leitura por conversa, sem a equipe
assert all(len(l) == len(cd.COLUNAS) for l in linhas)

# privacidade: nada do texto das mensagens na planilha; nada de nome ou telefone no log
assert not any(SEGREDO in str(v) for l in linhas for v in l)
log = saida.getvalue()
for proibido in (CLIENTE, LEAD, ANTIGO, "Cliente Inventado", "Lead Inventado", SEGREDO):
    assert proibido not in log, proibido
assert "27/11: 3 conversa(s), 2 sem resposta" in log, log

# simulação: não grava
ponte2 = FakePonte()
with contextlib.redirect_stdout(io.StringIO()):
    cd.rodada(FakeZaia(), FakeEJ(), ponte=ponte2, agora=AGORA, dias=[date(2026, 11, 27)], gravar=False)
assert ponte2.gravado is None

print("ok — conversas do dia")
