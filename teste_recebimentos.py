"""Teste da planilha mensal de parcelas com dados inventados (não chama a Za.Ia nem o EasyJur de verdade)."""
import io
import zipfile
import xml.dom.minidom
from datetime import date, datetime, timezone

import recebimentos as r
import secretaria

HOJE = date(2026, 11, 3)


def rec(i, venc, valor, cliente, status="A", parcela=None, parcelas=None, desc="HONORARIOS",
        plano="1.1.01 - Êxito", forma="PI", adv=None):
    return {"id": i, "status": status, "descricao": desc, "parcela": parcela, "parcelas": parcelas,
            "id_cliente": cliente, "forma_pagamento": forma, "tipo_receita": {"id": 3, "descricao": plano},
            "datas": {"vencimento": venc}, "valores": {"valor": valor}, "_adv": adv}


class FakeEJ:
    """Como o EasyJur: a listagem não traz o advogado (só o filtro id_advogado); vencida vem com status "A"
    e também aparece no filtro "V"."""

    def __init__(self, receitas, feriados=()):
        self.receitas, self.feriados, self.chamadas = receitas, set(feriados), []

    def chamar(self, f, **a):
        self.chamadas.append(f)
        if f == "list_receitas":
            ok = [x for x in self.receitas if x["datas"]["vencimento"] <= a["data_vencimento_fim"]
                  and (x["status"] == "A" if a["status"] == "A" else x["status"] == "A" and x["datas"]["vencimento"] < HOJE.isoformat())
                  and ("id_advogado" not in a or x["_adv"] == a["id_advogado"])]
            return {"data": [{k: v for k, v in x.items() if k != "_adv"} for x in ok], "meta": {"total_pages": 1}}
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
                plano="1.1.14 - Contencioso (Geral)", forma="BO", adv=378457),
            rec(11, "2026-11-05", 750, 1, parcela=4, parcelas=6, adv=344269),
            rec(12, "2026-11-10", 300, 1),                     # sem advogado
            rec(13, "2026-12-01", 999, 2, adv=344269),         # mês seguinte: fora
            rec(14, "2026-11-12", 50, 2, status="P"),          # paga: fora
            rec(15, "2026-10-20", 300, 2, parcela=1, parcelas=6, adv=344268),   # atrasada
            rec(16, "2026-09-23", 150, 1, plano="1.1.09 - Por Ato", adv=344269)]  # atrasada

# Dados: mês e atrasadas separados, advogado pelo filtro, dias em atraso
ej = FakeEJ(RECEITAS)
itens, atrasadas = r.dados(ej, 2026, 11, HOJE)
assert [x["id"] for x in itens] == [11, 12, 10] and [x["id"] for x in atrasadas] == [16, 15]
assert itens[0]["cliente"] == "Maria Da Silva" and itens[0]["parcela"] == "4/6" and itens[1]["parcela"] == "única"
assert itens[0]["espec"] == "Honorários — Êxito" and itens[0]["advogado"] == "Dra. Danielle"
assert itens[1]["advogado"] == "—" and itens[2]["advogado"] == "Dra. Fernanda" and itens[2]["forma"] == "Boleto"
assert atrasadas[0]["atraso"] == 41 and atrasadas[1]["atraso"] == 14 and atrasadas[1]["advogado"] == "Dr. Lucas"
assert itens[0]["situacao"] == "Em aberto"
assert ej.chamadas.count("get_pessoa") == 2  # um por cliente, nas duas abas
assert ej.chamadas.count("list_receitas") == 5  # A, V e um por advogado
print("OK — mês e atrasadas separados, com advogado e dias em atraso")

# Planilha: zip válido, 2 abas, XML bem formado, totais
xlsx = r.planilha_do_mes(itens, atrasadas, 2026, 11)
with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
    for n in z.namelist():
        if n.endswith(".xml") or n.endswith(".rels"):
            xml.dom.minidom.parseString(z.read(n))
    livro = z.read("xl/workbook.xml").decode()
    aba1, aba2 = z.read("xl/worksheets/sheet1.xml").decode(), z.read("xl/worksheets/sheet2.xml").decode()
assert 'name="Novembro 2026"' in livro and 'name="Atrasadas"' in livro
assert "Maria Da Silva" in aba1 and "SUM(C2:C4)" in aba1 and "<v>1185.08</v>" in aba1 and "Dra. Fernanda" in aba1
assert "Dias em atraso" in aba2 and "SUM(D2:D3)" in aba2 and "<v>450.0</v>" in aba2 and "<v>41</v>" in aba2
vazia = r.planilha_do_mes(itens, [], 2026, 11)
with zipfile.ZipFile(io.BytesIO(vazia)) as z:
    assert "Nenhuma parcela atrasada" in z.read("xl/worksheets/sheet2.xml").decode()
    xml.dom.minidom.parseString(z.read("xl/workbook.xml"))
assert r.brl(1185.08) == "R$ 1.185,08"
print("OK — planilha .xlsx válida com as abas do mês e de atrasadas")

# 1º dia útil: novembro/2026 começa num domingo e 02/11 é Finados -> 03/11
ej = FakeEJ(RECEITAS, feriados={"2026-11-02"})
assert r.primeiro_dia_util(ej, 2026, 11) == date(2026, 11, 3)
z = FakeZ()
assert r.rodada(z, ej, datetime(2026, 11, 2, 12, tzinfo=timezone.utc)) is False and not z.enviadas
assert r.rodada(z, ej, datetime(2026, 11, 3, 11, 30, tzinfo=timezone.utc)) is True
assert len(z.midias) == 1 and z.midias[0]["numero"] == "120363000000000001" and z.midias[0]["assinatura"] == "ia"
txt = z.enviadas[0]
assert txt.startswith("📊 *Parcelas a receber — novembro/2026*") and "R$ 1.185,08" in txt
assert "• 23/11 a 29/11: R$ 135,08 (1)" in txt
assert "Por advogado:\n• Dra. Danielle: R$ 750,00 (1)\n• Dra. Fernanda: R$ 135,08 (1)\n• Sem advogado: R$ 300,00 (1)" in txt
assert '⚠️ *Atrasadas de meses anteriores:* 2 parcela(s) · *R$ 450,00* (aba "Atrasadas" da planilha)' in txt
assert len(z.enviadas) == 1  # com a planilha, só o resumo
assert r.rodada(z, ej, datetime(2026, 11, 4, 11, 30, tzinfo=timezone.utc)) is False  # não repete
print("OK — envia no 1º dia útil, uma vez só, com totais por semana, por advogado e atrasadas")

# Prévia não conta como o envio oficial
z = FakeZ()
r.enviar(z, FakeEJ(RECEITAS), 2026, 11, previa=True, hoje=HOJE)
assert z.enviadas[0].startswith("📊 *Parcelas a receber — novembro/2026* (prévia)")
assert not r.ja_enviado(z, 2026, 11)
print("OK — prévia não bloqueia o envio do mês")

# Sem mídia no grupo: a lista vai em texto, com as atrasadas no fim
z = FakeZ(midia_ok=False)
r.enviar(z, FakeEJ(RECEITAS), 2026, 11, hoje=HOJE)
assert len(z.enviadas) == 2 and "Planilha completa" not in z.enviadas[0] and "(aba" not in z.enviadas[0]
assert z.enviadas[1].startswith("05/11 · *Maria Da Silva* · R$ 750,00 · parcela 4/6 · Honorários — Êxito · Dra. Danielle · Pix")
assert "⚠️ *Atrasadas de meses anteriores*\n23/09/2026 (41 dias) · *Maria Da Silva* · R$ 150,00" in z.enviadas[1]
print("OK — sem planilha, a lista sai em texto")

# Só a planilha: nenhum texto no grupo, nem quando o arquivo falha
for ok in (True, False):
    z = FakeZ(midia_ok=ok)
    r.enviar(z, FakeEJ(RECEITAS), 2026, 11, previa=True, so_planilha=True, hoje=HOJE)
    assert not z.enviadas and len(z.midias) == (1 if ok else 0)
heads = []
r.urllib.request.urlopen = lambda req, timeout=0: heads.append(req.get_header("User-agent")) or io.BytesIO(b"")
r.enviar(FakeZ(), FakeEJ(RECEITAS), 2026, 11, so_planilha=True, hoje=HOJE)
assert heads and heads[0].startswith("despachante-funil/")  # sem isso o Cloudflare da Za.Ia recusa o upload
print("OK — reenvio só da planilha, com identidade própria no upload")
