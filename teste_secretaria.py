"""Teste da secretaria sem IA, com dados inventados (não acessa nenhum sistema)."""
from datetime import date, datetime, timezone
import secretaria as s

s.COMECO = datetime(2026, 10, 1, tzinfo=timezone.utc)
AGORA = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)  # segunda-feira, 11h em Belém


class FakeZ:
    def __init__(self):
        self.enviadas, self.removidas = [], []

    def chamar(self, f, **a):
        if f == "enviar_mensagem":
            self.enviadas.append((a["numero"], a["texto"]))
        elif f == "buscar_contatos":
            return {"contatos": [{"id": "c9", "phone": a["query"],
                                  "labels": [{"id": "e13", "name": "PENDÊNCIA LUCAS"}, {"id": "e7", "name": "Cliente"}]}]}
        elif f == "remover_etiqueta_contato":
            self.removidas.append(a["etiquetaId"])
        return {}


class FakeEJ:
    def __init__(self):
        self.chamadas = []

    def chamar(self, f, **a):
        self.chamadas.append((f, a))
        if f == "e_feriado":
            return {"data": {"e_feriado": a["data"] == "2026-10-28"}}
        if f == "list_publicacoes" and "codPublicacao" in a:
            return {"data": [{"id": 501, "numProcesso": "0000137-11.2026.5.08.0114", "dataPublicacao": "2026-10-16"}]}
        if f == "list_publicacoes":
            return {"data": [{"id": 501}, {"id": 502}]}
        if f == "get_publicacao":
            return {"data": {"processo": {"id": 777}, "dataPublicacao": "2026-10-16"}}
        if f == "create_agenda":
            return {"data": {"id": 9001}}
        if f == "list_agenda":
            return {"data": [{"data": "2026-10-19", "hora_inicio": "14:00:00", "tipo": "AUDIENCIA", "status": "A",
                              "nome_cliente": "Cliente Teste", "descricao": "Audiência de instrução"},
                             {"data": "2026-10-19", "hora_inicio": "00:00:00", "tipo": "PRAZO", "status": "C",
                              "descricao": "já concluído"}]}
        return {"data": {}}


def msg(i, sender, texto, quando):
    return {"id": f"claude-mensagem-{i}", "sender": sender, "contentType": "CHAT", "content": texto,
            "createdAt": quando}


RESUMO = ("*Bom dia, Dra. Fernanda!* ☀️\n_Resumo de 16/10/2026_\n\n*📌 Publicações (2)*\n"
          "1. *0000137-11.2026.5.08.0114* — 2ª Vara do Trabalho\n   Fulano x Empresa\n   Intimação para manifestação\n"
          "   🔖 P-7925421011\n"
          "2. *0814563-68.2026.8.14.0040* — 1ª Vara Cível\n   Beltrana x Banco\n   Prazo de 15 dias\n   🔖 P-7925421099\n\n"
          "*📂 Andamentos (1)*\nA1. *0001261-22.2026.5.08.0130* — Ciclano: juntada de petição\n   🔖 A-111,112\n"
          "A2. *0809623-10.2026.8.14.0040* — Sicrano: audiência redesignada\n   📨 só no PJe\n"
          "   🔖 E-0809623-10.2026.8.14.0040\n")
FERN = s.ADVOGADAS_RESUMO[0]


def rodar_resumo(conversa):
    z, ej = FakeZ(), FakeEJ()
    s.comandos_do_resumo(z, lambda: ej, FERN, conversa, AGORA, {})
    return z, ej


# ---- leitura dos itens do resumo
it = s.itens_do_resumo(RESUMO)
assert it["1"]["ref"] == ("P", "7925421011") and it["A1"]["ref"] == ("A", "111,112")
assert it["A2"]["ref"][0] == "E" and it["2"]["processo"].startswith("0814563")
print("OK — itens do resumo")

# ---- formatos aceitos e ignorados
assert s.classificar_linha("Lida 1.")[0] == "LIDA"
assert s.classificar_linha("LIDAS 1, 3 e A2")[0] == "LIDA"
assert s.classificar_linha("lida todas")[0] == "LIDA"
assert s.classificar_linha("PRAZO 2 13/10 contestar")[0] == "PRAZO"
assert s.classificar_linha("agende na minha agenda Fernanda, atendimento teste para o dia 15/10/2026")[0] == "AGENDAR"
assert s.classificar_linha("MINHA AGENDA") == ("MINHA AGENDA", "")
assert s.classificar_linha("agenda Lucas") == ("AGENDA", "lucas")
for conversa in ("agenda a cliente para amanhã", "Lida a mensagem?", "Ok", "prazo do João é amanhã", "Não sei"):
    assert s.classificar_linha(conversa) is None, conversa
print("OK — só formatos exatos viram comando")

# ---- LIDA de publicação, andamento e evento só do PJe
s._feitos.clear()
conv = [msg(1, "AGENT", RESUMO, "2026-10-19T10:36:00.000Z"),
        msg(2, "CONTACT", "LIDA 1 A1 A2", "2026-10-19T13:00:00.000Z")]
z, ej = rodar_resumo(conv)
nomes = [c[0] for c in ej.chamadas]
assert nomes.count("atualizar_leitura_publicacao") == 2  # a publicação e a cópia 502
assert [c[1]["andamento_id"] for c in ej.chamadas if c[0] == "update_andamento"] == [111, 112]
texto = z.enviadas[0][1]
assert z.enviadas[0][0] == FERN["tel"] and "✅ Lida: item 1" in texto and "Ciente: item A2" in texto
assert s.marca(conv[1]) in texto
# na rodada seguinte a resposta já está na conversa: não executa de novo
s._feitos.clear()
z2, ej2 = rodar_resumo(conv + [msg(3, "AGENT", texto, "2026-10-19T13:02:00.000Z")])
assert not z2.enviadas and not ej2.chamadas
print("OK — LIDA executa uma vez só")

# ---- PRAZO: data interna 2 dias úteis antes, pulando fim de semana e feriado
s._feitos.clear()
z, ej = rodar_resumo([msg(1, "AGENT", RESUMO, "2026-10-19T10:36:00.000Z"),
                      msg(4, "CONTACT", "PRAZO 2 29/10 contestar", "2026-10-19T13:00:00.000Z")])
ag = [c[1] for c in ej.chamadas if c[0] == "create_agenda"][0]
assert ag["tipo"] == "PRAZO" and ag["data_fim"] == "2026-10-29" and ag["data"] == "2026-10-26"  # 28 é feriado
assert ag["id_advogado"] == 378457 and ag["id_advogado2"] == 344268 and ag["processo"] == 777
assert ag["codigo_publicacao"] == "7925421099" and "contestar (criado pelo WhatsApp)" == ag["descricao"]
assert "✅ Prazo criado: item 2" in z.enviadas[0][1] and "interno 26/10" in z.enviadas[0][1]
print("OK — PRAZO com data interna em dia útil")

# ---- AGENDAR: sem hora pergunta; com início e fim grava
s._feitos.clear()
z, ej = rodar_resumo([msg(5, "CONTACT", "Agendar 22/10 atendimento Patrícia", "2026-10-19T13:00:00.000Z")])
assert not ej.chamadas and "❓ Qual horário" in z.enviadas[0][1]
s._feitos.clear()
z, ej = rodar_resumo([msg(6, "CONTACT", "Agendar atendimento hoje 19/10/2026 as 16:30 até as 16:45, demarcar no google agenda",
                          "2026-10-19T13:00:00.000Z")])
ag = [c[1] for c in ej.chamadas if c[0] == "create_agenda"][0]
assert (ag["tipo"], ag["data"], ag["hora_inicio"], ag["hora_fim"]) == ("ATENDIMENTO", "2026-10-19", "16:30", "16:45")
assert "Google" in z.enviadas[0][1]
s._feitos.clear()
z, ej = rodar_resumo([msg(7, "CONTACT", "AGENDAR 1, 21/10 as 16:00. ASSUNTO: olhar decisão do processo",
                          "2026-10-19T13:00:00.000Z")])
ag = [c[1] for c in ej.chamadas if c[0] == "create_agenda"][0]
assert ag["hora_inicio"] == "16:00" and ag["hora_fim"] == "17:00" and ag["tipo"] == "TAREFA"
assert ag["descricao"].startswith("olhar decisão do processo")
print("OK — AGENDAR")

# ---- MINHA AGENDA lista só o que está em aberto
s._feitos.clear()
z, ej = rodar_resumo([msg(8, "CONTACT", "minha agenda", "2026-10-19T13:00:00.000Z")])
assert "Audiência de instrução" in z.enviadas[0][1] and "já concluído" not in z.enviadas[0][1]
print("OK — MINHA AGENDA")

# ---- comando antigo (mais de 24 h) é ignorado
s._feitos.clear()
z, ej = rodar_resumo([msg(1, "AGENT", RESUMO, "2026-10-16T10:36:00.000Z"),
                      msg(9, "CONTACT", "LIDA 1", "2026-10-17T10:00:00.000Z")])
assert not z.enviadas and not ej.chamadas
print("OK — comando antigo ignorado")

# ---- pendências do Dr. Lucas
REL = ("📋 *PENDÊNCIAS DR. LUCAS — 19/10/2026 — 17:30*\n━━━━━━━━\nTotal: 3 pendência(s)\n\n"
       "*[1]) MARIA TESTE* — 📞 5594900000001\n⚡ Urgência: ALTA\n✍️ Sugestão: \"Olá, Maria! Recebi seus documentos.\"\n\n"
       "*2) JOSÉ TESTE* — 📞 5594900000002\n✍️ Sugestão: \"Olá, José! ⟨informar o andamento⟩.\"  ⚠️ completar com EDITAR ou áudio\n\n"
       "*3) ANA TESTE* — 📞 5594900000003\n✍️ Sugestão: \"Olá, Ana! Vou verificar e te retorno.\"\n\n"
       "━━━━━━━━\n*Para responder aos clientes por aqui:*\n• *OK 2* — envia a sugestão 2\n")
_, itens = s.relatorio_lucas([msg(20, "AGENT", REL, "2026-10-18T20:39:00.000Z")], "2026-10-19")
assert set(itens) == {"1", "2", "3"} and itens["2"]["alerta"] and not itens["1"]["alerta"]


def rodar_lucas(texto):
    s._feitos.clear()
    z = FakeZ()
    conv = [msg(20, "AGENT", REL, "2026-10-18T20:39:00.000Z"), msg(21, "CONTACT", texto, "2026-10-19T12:00:00.000Z")]
    s.aprovacoes_lucas(z, conv, AGORA, {})
    return z


z = rodar_lucas("OK 1 2\nNão 3")
assert z.enviadas[0] == ("5594900000001", "*Dr. Lucas:*\nOlá, Maria! Recebi seus documentos.")
conf = z.enviadas[-1]
assert conf[0] == s.DR_LUCAS["tel"] and "✅ Enviado para MARIA TESTE (item 1)" in conf[1]
assert "❓ Item 2" in conf[1] and "⏭️ Item 3" in conf[1] and len(z.enviadas) == 2 and z.removidas == ["e13"]
z = rodar_lucas("EDITAR 2: Olá, José! O processo está concluso para sentença.\nAssim que sair, aviso.")
assert z.enviadas[0] == ("5594900000002", "*Dr. Lucas:*\nOlá, José! O processo está concluso para sentença.\nAssim que sair, aviso.")
z = rodar_lucas("ok todas")
assert [e[0] for e in z.enviadas[:-1]] == ["5594900000001", "5594900000003"]
z = rodar_lucas("Não lembrava disso")
assert not z.enviadas
print("OK — pendências do Dr. Lucas")

# ---- datas
assert s.data_br("13/10", date(2026, 10, 19)) == date(2027, 10, 13)
assert s.data_br("20/10", date(2026, 10, 19)) == date(2026, 10, 20)
assert s.horas("21/10 as 16:00") == ("16:00", None) and s.horas("19/10 14h30 até 15h") == ("14:30", "15:00")
print("OK — datas e horas")
