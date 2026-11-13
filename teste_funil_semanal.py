"""Teste do funil da semana com dados inventados (não chama a Za.Ia nem o EasyJur de verdade)."""
from datetime import date, datetime, timezone

import funil_semanal as f

SEXTA_1745 = datetime(2026, 11, 13, 20, 45, tzinfo=timezone.utc)  # 17h45 em Belém


def op(i, nome, status, cli, data="2026-11-12", enc=None, adv="Danielle Martins"):
    return {"id": i, "nome": nome, "status": status, "data": data, "data_encerramento": enc,
            "cliente_info": {"nome": cli}, "responsavel_info": {"nome": adv}}


def ag(i, data, status, nome, oport=None, cad="2026-11-10", hora="14:30", processo=0, pub=""):
    return {"id": i, "data": data, "status": status, "nome_cliente": nome, "oportunidade": oport,
            "data_cadastro": cad, "hora_inicio": hora, "processo": processo, "codigo_publicacao": pub}


OPS = [op(1, "Tráfego pago", "1", "Nereu Bonfim"), op(2, "Tráfego pago", "5", "Fabricia Coelho", enc="2026-11-13"),
       op(3, "Indicação Isaias", "5", "Faby Aguiar", data="2026-11-11", enc="2026-11-12"),
       op(4, "Cliente - Fernanda", "4", "Erica Ralane Carneiro", data="2026-11-13", enc="2026-11-13",
          adv="Fernanda Mesquita")]
ANTIGA = op(9, "Tráfego pago", "1", "Rogério", data="2026-11-05")
AGENDA = [ag(10, "2026-11-09", "C", "Rogério", oport=9, cad="2026-11-06"),
          dict(ag(11, "2026-11-09", "S", "Wan Lucia", cad="2026-11-05"), descricao="Reunião com lead — Wan (5575988059043)."),
          dict(ag(12, "2026-11-11", "A", "", hora="14:00", cad="2026-11-09"), descricao="Atendimento Érica, família.\n"),
          ag(13, "2026-11-12", "C", "Suane Lopes", hora="00:00", processo=55, pub="225"),  # publicação: fora
          ag(14, "2026-11-12", "C", "Faby Aguiar", oport=3, cad="2026-11-11"),
          ag(15, "2026-11-13", "A", "Moisés Neto", oport=1, cad="2026-11-13", hora="18:30")]  # ainda vai acontecer


class FakeEJ:
    def __init__(self):
        self.chamadas = []

    def chamar(self, ferr, page=1, page_size=100, **x):
        self.chamadas.append(ferr)
        if ferr == "list_oportunidades":
            if x.get("data_inicio") < "2026-11-09":
                dados = OPS + [ANTIGA]
            elif x.get("tipo_data") == "encerramento":
                dados = [o for o in OPS if o["status"] in x["status"] and x["data_inicio"] <= (o["data_encerramento"] or "") <= x["data_fim"]]
            else:
                dados = [o for o in OPS if x["data_inicio"] <= o["data"] <= x["data_fim"]]
        elif ferr == "list_agenda":
            if "data_cadastro_inicio" in x:
                dados = [a for a in AGENDA if x["data_cadastro_inicio"] <= a["data_cadastro"] <= x["data_cadastro_fim"]]
            else:
                dados = [a for a in AGENDA if x["data_interna_inicio"] <= a["data"] <= x["data_interna_fim"]]
        else:
            raise AssertionError(ferr)
        return {"data": [dict(d) for d in dados], "meta": {"total_pages": 1}}


class FakeZ:
    def __init__(self, grupo=None, limite=0):
        self.grupo, self.enviadas, self.limite = grupo or [], [], limite

    def chamar(self, ferr, **x):
        if self.limite:
            self.limite -= 1
            raise RuntimeError("Za.Ia.x: a ferramenta devolveu erro — Limite de 60 leituras por minuto do conector "
                               "Za.ia atingido. Esta chamada não foi executada: aguarde 0 segundos e tente novamente.")
        if ferr == "relatorio_atendimento":
            assert x["periodo"] == {"inicio": "2026-11-09T03:00:00.000Z", "fim": "2026-11-14T03:00:00.000Z"}
            return {"contatos": {"novos": 24, "reengajados": 49}}
        if ferr == "listar_contatos":
            assert x["etiqueta"] == "Tráfego Pago"
            return {"contatos": [{"phone": "5575988059043", "createdAt": "2026-11-04T14:01:29.442Z"},
                                 {"phone": "5592986106920", "createdAt": "2026-11-13T17:27:59.000Z"},
                                 {"phone": "5574998017910", "createdAt": "2026-11-13T12:29:44.000Z"}]}
        if ferr == "ler_grupo":
            return {"mensagens": self.grupo}
        if ferr == "enviar_mensagem_grupo":
            assert x["grupoId"] == "claude-grupo-1" and x["assinatura"] == "ia"
            self.enviadas.append(x["texto"])
            self.grupo.append({"sender": "AGENT", "content": "*Annie*:\n" + x["texto"]})
            return {}
        raise AssertionError(ferr)


assert f.semana(date(2026, 11, 13)) == (date(2026, 11, 9), date(2026, 11, 13))
assert f.semana(date(2026, 11, 15)) == (date(2026, 11, 9), date(2026, 11, 13))
assert f.origem("Tráfego pago") == "Tráfego pago" and f.origem("Indicação Isaias") == "Indicação"
assert f.origem("Trabalhista — Maria") == "Outros"

# fora de sexta ou antes das 17h30 não envia
z, ej = FakeZ(), FakeEJ()
assert f.rodada(z, ej, datetime(2026, 11, 12, 21, tzinfo=timezone.utc)) is None
assert f.rodada(z, ej, datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)) is None and not ej.chamadas

f.time.sleep = lambda s: None  # o limite por minuto da Za.Ia: espera e tenta de novo
z = FakeZ(limite=2)
msg = f.rodada(z, ej, SEXTA_1745)
assert z.enviadas == [msg] and msg.startswith("📊 *Funil da semana (09/11 a 13/11)*")
assert "👥 *Leads novos no WhatsApp* 24 (tráfego pago 2)" in msg and "(mais 49 contatos antigos" in msg
assert "📝 *Casos triados* 4 (tráfego pago 2, indicação 1, sem origem marcada 1)" in msg
assert "📅 *Reuniões agendadas na semana* 3" in msg  # 12, 14, 15 (a 10 e a 11 foram cadastradas antes)
assert "🗓️ *Reuniões marcadas para a semana* 5" in msg  # a da publicação fica fora
assert "✅ Realizadas 2" in msg and "❌ Canceladas 1 (Wan Lucia)" in msg
assert "❔ Sem baixa no EasyJur 1 (\"Atendimento Érica\" 11/11)" in msg and "⏳ Ainda vão acontecer 1" in msg
assert "🤝 *Contratos fechados* 1\nErica Ralane (sem origem marcada, Fernanda)" in msg and "🚫 *Não fecharam* 2" in msg
assert "Lead novo para reunião agendada 12%" in msg and "Reunião marcada para realizada 40%" in msg
assert "Reunião realizada para contrato 50%" in msg
# tráfego pago: leads 2 (etiqueta, contato novo na semana), triados 2 (Nereu, Fabricia), agendada 1 (Moisés),
# marcadas 3 (Rogério pelo nome da oportunidade, Moisés, Wan Lucia pela etiqueta do telefone da descrição)
assert "Leads 2, triados 2, reuniões agendadas 1, marcadas para a semana 3, realizadas 1, canceladas 1, contratos 0" in msg
assert "Lead do anúncio para reunião agendada 50%" in msg
assert ":" not in msg.split("\n", 1)[1].replace("17h30", ""), "sem dois-pontos no texto"

# 2ª tentativa das 18h: já está no grupo, não repete
assert f.rodada(z, ej, datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)) is None and len(z.enviadas) == 1
print("OK — funil da semana: contagens, origem, conversão, sem repetir e esperando o limite da Za.Ia")
