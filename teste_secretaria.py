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

# ---- aviso ao cliente a partir do resumo (CLIENTE 1 / CLIENTE A1: texto)
RESUMO_CLI = RESUMO.replace(
    "   🔖 P-7925421011\n",
    "   🔖 P-7925421011\n   📲 Para o cliente *Fulano* (📞 5594900000011):\n"
    "   \"Olá, Fulano! Saiu uma intimação no seu processo e já estamos cuidando.\"\n").replace(
    "   🔖 A-111,112\n",
    "   🔖 A-111,112\n   📲 Para o cliente *Ciclano* (📞 5594900000012):\n   \"Olá, Ciclano! ⟨completar⟩\"\n")
ras = s.rascunhos_cliente(RESUMO_CLI)
assert ras["1"] == {"nome": "Fulano", "tel": "5594900000011",
                    "texto": "Olá, Fulano! Saiu uma intimação no seu processo e já estamos cuidando."}
assert "2" not in ras and ras["A1"]["tel"] == "5594900000012"
assert s.itens_do_resumo(RESUMO_CLI)["1"]["ref"] == ("P", "7925421011")  # o 📲 não atrapalha o LIDA
assert s.classificar_linha("Cliente 1 e A1")[0] == "CLIENTE"
assert s.classificar_linha("CLIENTE T TODOS")[0] == "CLIENTE"
assert s.classificar_linha("cliente 2: Olá, Beltrana!")[0] == "CLIENTE_TEXTO"
assert s.classificar_linha("cliente ligou hoje") is None
s._feitos.clear()
z, ej = rodar_resumo([msg(1, "AGENT", RESUMO_CLI, "2026-10-19T10:36:00.000Z"),
                      msg(30, "CONTACT", "CLIENTE 1 A1\nLIDA 2", "2026-10-19T13:00:00.000Z")])
assert z.enviadas[0] == ("5594900000011", "*Dra. Fernanda Mesquita:*\nOlá, Fulano! Saiu uma intimação no seu "
                                          "processo e já estamos cuidando.")
conf = z.enviadas[-1][1]
assert "✅ Cliente avisado: item 1 — Fulano" in conf and "❓ O rascunho do item A1 está incompleto" in conf
assert "✅ Lida: item 2" in conf and len(z.enviadas) == 2
# repetir CLIENTE 1 depois do envio não manda de novo
s._feitos.clear()
z, ej = rodar_resumo([msg(1, "AGENT", RESUMO_CLI, "2026-10-19T10:36:00.000Z"),
                      msg(31, "AGENT", conf, "2026-10-19T13:01:00.000Z"),
                      msg(32, "CONTACT", "cliente 1", "2026-10-19T13:30:00.000Z")])
assert len(z.enviadas) == 1 and "já foi enviado" in z.enviadas[0][1]
# texto do advogado, em duas linhas
s._feitos.clear()
z, ej = rodar_resumo([msg(1, "AGENT", RESUMO_CLI, "2026-10-19T10:36:00.000Z"),
                      msg(33, "CONTACT", "CLIENTE A1: Olá, Ciclano!\nO juiz marcou audiência.", "2026-10-19T13:00:00.000Z")])
assert z.enviadas[0] == ("5594900000012", "*Dra. Fernanda Mesquita:*\nOlá, Ciclano!\nO juiz marcou audiência.")
# item sem rascunho
s._feitos.clear()
z, ej = rodar_resumo([msg(1, "AGENT", RESUMO_CLI, "2026-10-19T10:36:00.000Z"),
                      msg(34, "CONTACT", "cliente 2", "2026-10-19T13:00:00.000Z")])
assert len(z.enviadas) == 1 and "não tem rascunho" in z.enviadas[0][1]
print("OK — CLIENTE a partir do resumo")

# ---- retorno mensal (itens T) no privado do Dr. Lucas: só CLIENTE é executado ali
import retorno as rt
proc = {"numero": "0810786-75.2026.8.14.0040", "ultimo_andamento": "10/09/2026 - Conclusos para julgamento"}
assert "está com o juiz" in rt.frase_processo(proc) and "10/09/2026" in rt.frase_processo(proc)
assert rt.frase_processo({"tipo_processo": "administrativo"}).startswith("o seu requerimento")
partes = rt.mensagens(rt.ADVOGADOS[344268], [("Maria Teste", "5594900000021", [proc])])
assert len(partes) == 1 and partes[0].startswith(s.INICIO_RETORNO)
ras = s.rascunhos_cliente(partes[0])
assert ras["T1"]["tel"] == "5594900000021" and ras["T1"]["texto"].startswith("Olá, Maria! Passando para dar notícias")
grande = rt.mensagens(rt.ADVOGADOS[344269], [(f"Cliente {i}", f"55949000001{i:02d}", [proc]) for i in range(20)])
assert len(grande) > 1 and all(len(p) < 3800 for p in grande) and "(1/" in grande[0]
assert len(s.rascunhos_cliente("\n".join(grande))) == 20
s._feitos.clear()
z = FakeZ()
conv = [msg(40, "AGENT", partes[0], "2026-10-19T12:00:00.000Z"),
        msg(41, "CONTACT", "CLIENTE T TODOS\nAGENDAR 22/10 14h teste", "2026-10-19T13:00:00.000Z")]
s.comandos_do_resumo(z, lambda: FakeEJ(), s.DR_LUCAS, conv, AGORA, {}, so_cliente=True)
assert z.enviadas[0][0] == "5594900000021" and z.enviadas[0][1].startswith("*Dr. Lucas:*\nOlá, Maria!")
assert "📅" not in z.enviadas[-1][1]  # o AGENDAR do Dr. Lucas fica para o Secretário com IA
# fatia: cada cliente cai em exatamente um dia a cada 20 dias úteis
from datetime import timedelta as _td
dias = [date(2026, 10, 19) + _td(days=i) for i in range(28)]
uteis = [d for d in dias if d.weekday() < 5]
assert sum(rt.da_fatia(686470823, d) for d in uteis[:20]) == 1
print("OK — retorno mensal")

# ---- retorno mensal de ponta a ponta (sistemas falsos)
HOJE_R = datetime(2026, 10, 20, 12, 30, tzinfo=timezone.utc)  # terça, 9h30 em Belém
idx = rt.dia_util_indice(date(2026, 10, 20)) % rt.CICLO
cid_sim, cid_nao, cid_contato = 1000 * rt.CICLO + idx, 1000 * rt.CICLO + (idx + 1) % rt.CICLO, 2000 * rt.CICLO + idx


class EJR(FakeEJ):
    def chamar(self, f, **a):
        self.chamadas.append((f, a))
        if f == "list_processos":
            return {"data": [{"id_cliente": c, "nome_cliente": n, "id_advogado": adv, "numero": "0001-1",
                              "ultimo_andamento": "01/09/2026 - Juntada de petição"}
                             for c, n, adv in ((cid_sim, "JOANA TESTE", 378457), (cid_nao, "PEDRO", 344269),
                                               (cid_contato, "RITA TESTE", 354290))],
                    "meta": {"total_pages": 1}}
        if f == "get_pessoa":
            return {"data": {"celular": "(94) 99000-%04d" % (a["pessoa_id"] // 1000)}}
        return super().chamar(f, **a)


class ZR(FakeZ):
    def chamar(self, f, **a):
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": a["telefone"], "lastMessageAt": "2026-10-15T12:00:00Z"}}
        if f == "ler_conversa":
            if a["conversaId"].endswith("%04d" % (cid_contato // 1000)):  # Rita recebeu mensagem da advogada
                return {"messages": [msg(50, "USER", "*Dra Danielle Esteves*: Olá!", "2026-10-10T12:00:00Z")]}
            return {"messages": []}
        return super().chamar(f, **a)


rt._estado["feito"] = None
z, ej = ZR(), EJR()
rt.rodada(z, lambda: ej, HOJE_R, {})
assert len(z.enviadas) == 1 and z.enviadas[0][0] == "5594991742534"   # só a Joana, para a Dra. Fernanda
assert "*Joana Teste*" in z.enviadas[0][1] and "foram juntados documentos" in z.enviadas[0][1]
assert sum(1 for c in ej.chamadas if c[0] == "get_pessoa") == 2          # Pedro nem é consultado hoje
n_antes = len(ej.chamadas)
rt.rodada(z, lambda: ej, HOJE_R, {})                                    # segunda chamada no mesmo dia: nada
assert len(ej.chamadas) == n_antes and len(z.enviadas) == 1
print("OK — retorno mensal de ponta a ponta")
