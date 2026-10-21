"""Teste da planilha mensal de parcelas com dados inventados (não chama a Za.Ia nem o EasyJur de verdade)."""
import io
import zipfile
import xml.dom.minidom
from datetime import date, datetime, timezone

import recebimentos as r
import secretaria


def rec(i, venc, valor, cliente, status="A", parcela=None, parcelas=None, desc="HONORARIOS",
        plano="1.1.01 - Êxito", forma="PI"):
    return {"id": i, "status": status, "descricao": desc, "parcela": parcela, "parcelas": parcelas,
            "id_cliente": cliente, "forma_pagamento": forma, "tipo_receita": {"id": 3, "descricao": plano},
            "datas": {"vencimento": venc}, "valores": {"valor": valor}}


class FakeEJ:
    def __init__(self, receitas, feriados=()):
        self.receitas, self.feriados, self.chamadas = receitas, set(feriados), []

    def chamar(self, f, **a):
        self.chamadas.append(f)
        if f == "list_receitas":
            ok = [x for x in self.receitas if x["status"] == a["status"]
                  and a["data_vencimento_inicio"] <= x["datas"]["vencimento"] <= a["data_vencimento_fim"]]
            return {"data": ok, "meta": {"total_pages": 1}}
        if f == "get_pessoa":
            return {"data": {"nome": {1: "MARIA DA SILVA", 2: "joão souza"}[a["pessoa_id"]]}}
        if f == "e_feriado":
            return {"data": {"e_feriado": a["data"] in self.feriados}}
        raise AssertionError(f)


class FakeZ:
    def __init__(self, grupo=None, midia_ok=True):
        self.grupo, self.midia_ok, self.enviadas, self.midias = grupo or [], midia_ok, [], []

    def chamar(self, f, **a):
        if f == "ler_grupo":
            return {"mensagens": self.grupo}
        if f == "enviar_mensagem_grupo":
            assert a["assinatura"] == "ia" and a["grupoId"] == "claude-grupo-18"
            self.enviadas.append(a["texto"])
            self.grupo.append({"sender": "AGENT", "content": "*Annie*:\n" + a["texto"]})
            return {}
        if f == "buscar_contatos":
            return {"contatos": [{"name": "Cynthia- Setor financeiro", "phone": None},
                                 {"name": "Financeiro Escritório", "phone": "120363000000000001"}]}
        if f == "preparar_upload_midia":
            if not self.midia_ok:
                raise RuntimeError("grupo não aceita mídia")
            return {"uploadUrl": "http://teste", "uploadKey": "k1"}
        if f == "enviar_midia":
            self.midias.append(a)
            return {}
        raise AssertionError(f)


r.urllib.request.urlopen = lambda req, timeout=0: io.BytesIO(b"")  # o PUT do upload não sai do teste
secretaria._feriados.clear()

RECEITAS = [rec(10, "2026-11-28", 135.08, 2, parcela=11, parcelas=12, desc="OPERACIONAL",
                plano="1.1.14 - Contencioso (Geral)", forma="BO"),
            rec(11, "2026-11-05", 750, 1, parcela=4, parcelas=6),
            rec(12, "2026-11-10", 300, 1, status="V"),
            rec(13, "2026-12-01", 999, 2),          # fora do mês
            rec(14, "2026-11-12", 50, 2, status="P")]  # paga: fica de fora

# Planilha: zip válido, XML bem formado, ordem por vencimento, total e nomes
ej = FakeEJ(RECEITAS)
itens = r.linhas(ej, r.receitas_do_mes(ej, 2026, 11))
assert [x["id"] for x in itens] == [11, 12, 10]
assert itens[0]["cliente"] == "Maria Da Silva" and itens[0]["parcela"] == "4/6" and itens[1]["parcela"] == "única"
assert itens[0]["espec"] == "Honorários — Êxito"
assert itens[2]["espec"] == "Operacional — Contencioso (Geral)" and itens[2]["forma"] == "Boleto"
assert itens[1]["situacao"] == "Vencida"
assert ej.chamadas.count("get_pessoa") == 2  # um por cliente
xlsx = r.planilha(itens, "Novembro 2026")
with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
    for n in z.namelist():
        if n.endswith(".xml") or n.endswith(".rels"):
            xml.dom.minidom.parseString(z.read(n))
    folha = z.read("xl/worksheets/sheet1.xml").decode()
assert "Maria Da Silva" in folha and "SUM(C2:C4)" in folha and "<v>1185.08</v>" in folha
assert r.brl(1185.08) == "R$ 1.185,08"
print("OK — planilha .xlsx válida, ordenada e com total")

# 1º dia útil: novembro/2026 começa num domingo e 02/11 é Finados -> 03/11
ej = FakeEJ(RECEITAS, feriados={"2026-11-02"})
assert r.primeiro_dia_util(ej, 2026, 11) == date(2026, 11, 3)
z = FakeZ()
assert r.rodada(z, ej, datetime(2026, 11, 2, 12, tzinfo=timezone.utc)) is False and not z.enviadas
assert r.rodada(z, ej, datetime(2026, 11, 3, 11, 30, tzinfo=timezone.utc)) is True
assert len(z.midias) == 1 and z.midias[0]["numero"] == "120363000000000001" and z.midias[0]["assinatura"] == "ia"
assert z.enviadas[0].startswith("📊 *Parcelas a receber — novembro/2026*") and "R$ 1.185,08" in z.enviadas[0]
assert len(z.enviadas) == 1  # com a planilha, só o resumo
assert "• 23/11 a 29/11: R$ 135,08 (1)" in z.enviadas[0]
r.enviar(FakeZ(), FakeEJ([rec(20, "2026-11-30", 10, 1)]), 2026, 11, dry_run=True)
assert "• 30/11: R$ 10,00 (1)" in r.resumo(r.linhas(FakeEJ([rec(20, "2026-11-30", 10, 1)]), [rec(20, "2026-11-30", 10, 1)]), 2026, 11)
assert r.rodada(z, ej, datetime(2026, 11, 4, 11, 30, tzinfo=timezone.utc)) is False  # não repete
print("OK — envia no 1º dia útil, uma vez só")

# Prévia não conta como o envio oficial
z = FakeZ()
r.enviar(z, FakeEJ(RECEITAS), 2026, 11, previa=True)
assert z.enviadas[0].startswith("📊 *Parcelas a receber — novembro/2026* (prévia)")
assert not r.ja_enviado(z, 2026, 11)
print("OK — prévia não bloqueia o envio do mês")

# Sem mídia no grupo: a lista vai em texto
z = FakeZ(midia_ok=False)
r.enviar(z, FakeEJ(RECEITAS), 2026, 11)
assert len(z.enviadas) == 2 and "Planilha completa" not in z.enviadas[0]
assert z.enviadas[1].startswith("05/11 · *Maria Da Silva* · R$ 750,00 · parcela 4/6")
print("OK — sem planilha, a lista sai em texto")
