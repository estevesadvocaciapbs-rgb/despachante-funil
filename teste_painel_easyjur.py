"""Testes offline do painel_easyjur.py. Só dados inventados. Rodar: python teste_painel_easyjur.py"""
import contextlib
import io
from datetime import datetime, timezone

import painel_easyjur as pe

AGORA = datetime(2026, 11, 27, 22, 55, tzinfo=timezone.utc)
SEGREDO = "Cliente Inventado da Silva"


class FakeEJ:
    def __init__(self):
        self.filtros = []

    def chamar(self, ferr, **x):
        self.filtros.append((ferr, x))
        if ferr == "list_agenda":
            assert x["tipo"] == "PRAZO" and x["data_interna_inicio"] == "2026-11-20" and x["data_interna_fim"] == "2026-12-04"
            if x["page"] == 1:
                return {"data": [{"id": 1, "data": "2026-11-28", "data_cadastro": "2026-11-20", "status": "A",
                                  "advogado": "Adv Teste", "cliente": 900, "nome_cliente": SEGREDO, "processo": 5,
                                  "descricao": "Prazo para  réplica\n"}], "meta": {"total_pages": 2}}
            return {"data": [{"id": 2, "data": "2026-11-25", "status": "C", "cliente": 0, "nome_cliente": "",
                              "descricao": "x" * 400}], "meta": {"total_pages": 2}}
        if ferr == "list_processos":
            return {"data": [{"id_cliente": 900, "nome_cliente": SEGREDO}, {"id_cliente": 900, "nome_cliente": SEGREDO},
                             {"id_cliente": 901, "nome_cliente": "Outro Inventado"}, {"id_cliente": None}],
                    "meta": {"total_pages": 1}}
        raise AssertionError(ferr)


gravado = {}


def ponte(acao, **x):
    gravado[acao] = x
    return {"ok": True, "prazos": len(x["prazos"]), "clientes": len(x["clientes"])}


saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    pz, cl = pe.rodada(FakeEJ(), ponte=ponte, agora=AGORA)
assert [p["id"] for p in pz] == [1, 2]
assert pz[0]["descricao"] == "Prazo para réplica" and len(pz[1]["descricao"]) == 300
assert sorted((c["id_pessoa"], c["processos"]) for c in cl) == [("900", 2), ("901", 1)]
assert gravado["painel_easyjur"]["prazos"] == pz
log = saida.getvalue()
assert SEGREDO not in log and "réplica" not in log and "Outro Inventado" not in log, log
assert "2 prazo(s) entre 20/11 e 04/12 (1 em aberto); 2 cliente(s)" in log, log

gravado.clear()
with contextlib.redirect_stdout(io.StringIO()):
    pe.rodada(FakeEJ(), ponte=ponte, agora=AGORA, gravar=False)
assert not gravado
print("ok — painel EasyJur")
