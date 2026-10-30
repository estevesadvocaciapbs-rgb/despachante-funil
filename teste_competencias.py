"""Teste do acerto da competência das parcelas, com dados inventados (não acessa nenhum sistema)."""
from datetime import datetime, timezone

import competencias as c

SEIS = datetime(2026, 11, 3, 9, 10, tzinfo=timezone.utc)   # 6h10 em Belém
OITO = datetime(2026, 11, 3, 11, 10, tzinfo=timezone.utc)  # 8h10 em Belém


def rec(i, venc, comp):
    return {"id": i, "datas": {"vencimento": venc, "competencia": comp}}


class Ej:
    def __init__(self, abertas, recusa=()):
        self.abertas, self.recusa, self.feitas = abertas, recusa, []

    def chamar(self, f, **a):
        if f == "list_receitas":
            return {"data": self.abertas if a["status"] == "A" else [], "meta": {"total_pages": 1}}
        if a["receita_id"] in self.recusa:
            raise RuntimeError("409")
        self.feitas.append((a["receita_id"], a["data_competencia"]))


def rodar(ej, agora=SEIS):
    c._estado["dia"] = None
    logs = []
    c.rodada(lambda: ej, agora, logs.append)
    return logs


# acerta só parcela com mês diferente, inclusive sem competência
ej = Ej([rec(1, "2026-12-10", "2026-11-10"), rec(2, "2026-11-10", "2026-11-03"), rec(3, "2026-11-10", None)])
assert "2 parcela(s) acertada(s), 0 recusada(s)" in rodar(ej)[0]
assert ej.feitas == [(1, "2026-12-10"), (3, "2026-11-10")]
print("OK — acerta só a parcela com mês diferente")

# fora das 6h não roda; às 6h roda uma vez por dia
ej = Ej([rec(1, "2026-12-10", "2026-11-10")])
assert not rodar(ej, OITO) and not ej.feitas
rodar(ej)
c.rodada(lambda: ej, SEIS)
assert len(ej.feitas) == 1
print("OK — só às 6h, uma vez por dia")

# recusada pela API não derruba o resto
ej = Ej([rec(1, "2026-12-10", "2026-11-10"), rec(2, "2027-01-10", "2026-11-10")], recusa=(1,))
assert "1 parcela(s) acertada(s), 1 recusada(s)" in rodar(ej)[0]
print("OK — recusa da API não derruba o resto")
