"""Teste das regras do despachante sem acessar nenhum sistema (dados simulados)."""
from datetime import datetime
import despachante as d

AGORA = datetime(2026, 10, 2, 18, 0, tzinfo=d.BRT)  # sexta-feira, 18h


class FakeEJ:
    def __init__(self, itens):
        self.itens = itens

    def chamar(self, ferramenta, **a):
        if ferramenta == "e_feriado":
            return {"data": {"e_feriado": a["data"] == "2026-10-12"}}
        if ferramenta == "list_agenda":
            return {"data": [i for i in self.itens if i["_adv"] == a["id_responsavel_qualquer"]],
                    "meta": {"total_pages": 1}}


def item(adv, dia, tipo, h0="00:00", h1="00:00", status="A", dia_fim=None):
    return {"_adv": adv, "data": dia, "data_fim": dia_fim or dia, "tipo": tipo, "status": status,
            "hora_inicio": h0 + ":00", "hora_fim": h1 + ":00"}


itens = [
    item(344269, "2026-10-05", "ATENDIMENTO", "10:00", "10:30"),   # ocupa seg 10h
    item(344269, "2026-10-05", "PRAZO"),                            # não ocupa
    item(344269, "2026-10-06", "VIAGEM"),                           # terça inteira bloqueada
    item(344269, "2026-10-07", "AUDIENCIA", "14:00", "15:00"),     # quarta 14h e 14h30 ocupados
    item(378457, "2026-10-05", "AUDIENCIA", "08:00", "09:00"),     # Fernanda: segunda bloqueada
    item(378457, "2026-10-06", "AUDIENCIA", status="S"),           # cancelada: não bloqueia
]
ag = d.Agenda(FakeEJ(itens), AGORA)
print("dias possíveis:", [x.isoformat() for x in ag.dias_possiveis()])
liv_d = ag.livres(d.DANIELLE, set())
assert all(s.strftime("%d/%m") != "06/10" for s in liv_d), "viagem deveria bloquear a terça"
assert not any(s.strftime("%d/%m %H:%M") == "05/10 10:00" for s in liv_d), "10h de segunda ocupado"
assert not any(s.strftime("%d/%m %H:%M") in ("07/10 14:00", "07/10 14:30") for s in liv_d)
assert all(s.strftime("%d/%m") != "12/10" for s in liv_d), "feriado"
liv_f = ag.livres(d.FERNANDA, set())
assert all(s.strftime("%d/%m") != "05/10" for s in liv_f), "dia de audiência bloqueado"

dois = d.manha_e_tarde(liv_d)
print("2 horários Danielle:", [d.texto_slot(s) for s in dois])
assert len(dois) == 2 and dois[0].hour < 12 <= dois[1].hour
dois_f = d.manha_e_tarde(liv_f)
print("2 horários Fernanda:", [d.texto_slot(s) for s in dois_f])
assert [s.strftime("%H:%M") for s in dois_f] == ["09:30", "14:30"]

seg_cedo = d.Agenda(FakeEJ([]), datetime(2026, 10, 5, 7, 0, tzinfo=d.BRT))  # segunda 7h
dois_seg = d.manha_e_tarde(seg_cedo.livres(d.DANIELLE, set()))
print("lead de segunda 7h ->", [d.texto_slot(s) for s in dois_seg])
assert [s.strftime("%d/%m %H:%M") for s in dois_seg] == ["06/10 10:00", "06/10 14:00"], \
    "deve ser o próximo dia útil, nunca o mesmo dia"

grupo = {"mensagens": [
    {"sender": "AGENT", "createdAt": "2026-10-02T20:56:46.313Z", "content":
     "Contato - *Bernardo* (5594900000099)\n*🆕 NOVO LEAD · Trabalhista — Rescisão Indireta (Outros Motivos)*\n"
     "‼️NOVA OPORTUNIDADE‼️\nLEAD: Bernardo (não informado)\nÁREA: Trabalhista — Rescisão Indireta\n"
     "RESPONSÁVEL: Dra. Danielle Esteves\n\nBernardo, Auxiliar de Produção, dois anos de empresa, "
     "salário atrasado e FGTS sem depósito.\n\nPonto a verificar com Dra. Danielle Esteves: viabilidade."},
    {"sender": "AGENT", "createdAt": "2026-10-02T19:00:00.000Z", "content":
     "‼️NOVA OPORTUNIDADE‼️\nLEAD: Maria (5594999990000)\nÁREA: Trabalhista\n"
     "Contrato de experiência de 30 dias, salário de R$ 1.600"},
    {"sender": "AGENT", "createdAt": "2026-10-02T19:00:00.000Z", "content":
     "Contato - *Ana* (5594999990001)\n🔔 Novo lead — Criminal\nURGENTE"},
    {"sender": "AGENT", "createdAt": "2026-10-02T19:00:00.000Z", "content":
     "Contato - *Rita* (5594999990002)\n‼️NOVA OPORTUNIDADE‼️\nÁREA: Previdenciário\n"
     "RESPONSÁVEL: Dra. Fernanda Mesquita (pedido do cliente)"},
]}
tarefas = [
    {"title": "🆕 NOVO LEAD · Família — Guarda", "createdAt": "2026-10-02T20:00:00.000Z",
     "description": "‼️NOVA OPORTUNIDADE‼️\nLEAD: Joana (5594988887777)\nÁREA: Família — Guarda\n"
                    "Separada há 1 ano, quer regularizar a guarda do filho.\n\nResumo do atendimento:\n"
                    "raciocínio interno que não deve aparecer\n\nDepartamento: familia_guarda_visitas\n"
                    "Contato: Joana (5594988887777)"},
    {"title": "Contato encaminhado pelo Suporte - Bernardo", "createdAt": "2026-10-02T20:00:00.000Z",
     "description": "🔔 O briefing vem no ‼️NOVA OPORTUNIDADE‼️ enviado ao grupo\n"
                    "Departamento: suporte\nContato: Bernardo (5594900000099)"},
]
leads = d.leads_recentes(grupo, tarefas, datetime(2026, 10, 2, 18, 30, tzinfo=d.BRT))
for lead in leads:
    area, pular = d.classificar(lead["texto"])
    print(f"{lead['nome']} ({lead['origem']}) -> {area} {pular or ''} | viabilidade reprova: "
          f"{d.reprova_viabilidade(lead['texto'])} | pediu Fernanda: {d.pediu_fernanda(lead['texto'])}")
joana = next(l for l in leads if l["nome"] == "Joana")
assert joana["origem"] == "tarefa"
assert "raciocínio" not in d.resumo_do_caso(joana["texto"])
print("resumo Joana:", d.resumo_do_caso(joana["texto"]))
print("resumo Bernardo:", d.resumo_do_caso(next(l for l in leads if l["nome"] == "Bernardo")["texto"]))

conf = "Seu atendimento com a Dra. Danielle Esteves ficou marcado para segunda-feira, 05/10, às 10h00."
achado = d.RE_SLOT.search(conf.split(d.MARCA_CONFIRMACAO, 1)[1])
assert d.data_do_texto(*achado.groups(), AGORA) == datetime(2026, 10, 5, 10, 0, tzinfo=d.BRT)

oferta = ("Olá, X! A Dra. Danielle Esteves analisou o seu caso e pode te atender por videochamada. "
          "Tenho estes horários: 1) segunda-feira, 05/10, às 10h30; 2) segunda-feira, 05/10, às 14h00. Qual?")
res = d.reservas_recentes([{"content": oferta, "scheduledAt": "2026-10-02T21:00:00.000Z"}],
                          datetime(2026, 10, 2, 18, 30, tzinfo=d.BRT))
assert not any(s.strftime("%d/%m %H:%M") == "05/10 10:30" for s in ag.livres(d.DANIELLE, res))
print("OK — todas as verificações passaram")

# ---- viabilidade trabalhista (critérios do Gem/POP)
AG = datetime(2026, 10, 2, 19, 45, tzinfo=d.BRT)
faby = ("‼️NOVA OPORTUNIDADE‼️\nLEAD: Faby (5594900000088)\nÁREA: Trabalhista\n"
        "A senhora é auxiliar de chão em uma malharia, recebe salário mínimo e ainda está trabalhando lá. "
        "Começou no dia 12/08, fez 4 dias de experiência e não recebeu por um dia em que fez exame admissional.")
av = d.avaliar_trabalhista(faby, AG)
print("Faby ->", av["nota"], av["eixos"], av["dias"], av["motivo"])
assert not av["agenda"], "Faby não deve receber horário automático"
bern = ("‼️NOVA OPORTUNIDADE‼️\nÁREA: Trabalhista — Rescisão Indireta\nBernardo, Auxiliar de Produção, "
        "dois anos de empresa, salário atrasado e FGTS sem depósito.")
av = d.avaliar_trabalhista(bern, AG)
print("Bernardo ->", av["nota"], av["eixos"], av["dias"], av["motivo"])
assert av["agenda"]
gest = "ÁREA: Trabalhista — Gestante\nTrabalha há 2 meses, está grávida de 3 meses e foi demitida."
assert d.avaliar_trabalhista(gest, AG)["agenda"]
semreg = "ÁREA: Trabalhista\nTrabalha há 1 mês sem carteira assinada, salário mínimo."
av = d.avaliar_trabalhista(semreg, AG)
print("Sem registro 1 mês ->", av["nota"], av["eixos"], av["motivo"])
assert not av["agenda"], "sem registro curto não é exceção"
semreg2 = "ÁREA: Trabalhista\nTrabalha há 3 anos sem carteira assinada, faz hora extra sem receber."
av = d.avaliar_trabalhista(semreg2, AG)
print("Sem registro 3 anos ->", av["nota"], av["eixos"], av["motivo"])
assert av["agenda"]
grupo_ag = {"mensagens": [{"sender": "CONTACT", "content": "AGENDAR Faby"}]}
assert d.liberado_pelo_grupo({"nome": "Faby Aguiar", "tel": "5594900000088"}, grupo_ag)
assert not d.liberado_pelo_grupo({"nome": "Maria", "tel": "5594900000077"}, grupo_ag)
print("OK — viabilidade conferida")

# ---- retomada de conversa parada (caso Júlia, 02/10)
AGR = datetime(2026, 10, 3, 0, 19, 0, tzinfo=d.timezone.utc)
julia = [
    {"sender": "CONTACT", "content": "Registro com ponto eletrônico", "createdAt": "2026-10-03T00:14:57.000Z"},
    {"sender": "AGENT", "content": "*Annie*:\nA senhora registra a jornada por ponto eletrônico. Isso é uma informação "
     "importante para o seu caso.", "createdAt": "2026-10-03T00:15:48.003Z"},
]
assert d.precisa_retomar(julia, AGR), "Júlia parada há 3 min sem pergunta: deve retomar"
assert not d.precisa_retomar(julia, datetime(2026, 10, 3, 0, 16, 30, tzinfo=d.timezone.utc)), "cedo demais"
com_pergunta = julia[:1] + [{"sender": "AGENT", "content": "*Annie*:\nE qual é a média do seu salário?",
                             "createdAt": "2026-10-03T00:15:48.003Z"}]
assert not d.precisa_retomar(com_pergunta, AGR)
encerrou = julia[:1] + [{"sender": "AGENT", "content": "*Annie*:\nPerfeito! A equipe vai te chamar por aqui para "
                         "combinar o horário.", "createdAt": "2026-10-03T00:15:48.003Z"}]
assert not d.precisa_retomar(encerrou, AGR)
respondeu = julia + [{"sender": "CONTACT", "content": "R$ 4.000", "createdAt": "2026-10-03T00:17:00.000Z"}]
assert not d.precisa_retomar(respondeu, AGR), "cliente já respondeu"
ja = julia + [{"sender": "USER", "content": "*Annie*:\nJúlia, " + d.MARCA_RETOMADA + ", pode...?",
               "createdAt": "2026-10-03T00:18:00.000Z"}]
assert not d.precisa_retomar(ja, AGR)
print("OK — retomada conferida")

# ---- violência doméstica marcada "URGENTE" recebe horário (não é pulada)
vd = "⚠️ URGENTE · Família — Violência Doméstica\n‼️NOVA OPORTUNIDADE‼️\nÁREA: Família — Violência Doméstica"
assert d.classificar(vd) == ("vd", None), d.classificar(vd)
crim = "🚨 URGENTE · Criminal — Fulano\nÁREA: Criminal\nURGÊNCIA: preso agora"
assert d.classificar(crim)[1] == "urgente"
print("OK — violência doméstica e criminal urgente")

# ---- confirmação sem "ficou marcado para" (caso real de 06/10, nome trocado)
oferta_h = ("Olá, Helena! O Dr. Lucas analisou o seu caso e pode te atender por videochamada. Tenho estes horários: "
            "1) quarta-feira, 07/10, às 12h30; 2) quinta-feira, 08/10, às 10h30. Qual fica melhor pra você?")
ofertados = set(d.RE_SLOT.findall(oferta_h))
conf_h = "*Annie*:\nPerfeito, Helena Souza! O atendimento com o Dr. Lucas será amanhã, quarta-feira, 07/10, às 12h30, por videochamada."
bate = [s for s in d.RE_SLOT.findall(conf_h) if s in ofertados]
assert bate == [("07", "10", "12", "30")], bate
assert len([s for s in d.RE_SLOT.findall(oferta_h) if s in ofertados]) == 2  # repetir a oferta não confirma
print("OK — confirmação pelo horário citado")

# ---- atendimento concluído no EasyJur encerra a conversa na Za.Ia (caso real de 06/10, nome trocado)
class FakeZ:
    def __init__(self, msgs, status="OPEN"):
        self.msgs, self.status, self.encerradas = msgs, status, []
    def chamar(self, f, **a):
        if f == "buscar_contatos":
            return {"contatos": [{"name": "Mateus Ferreira", "phone": "5594900000077"}]}
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": "c1", "status": self.status, "contact": {"name": "Mateus Ferreira"}}}
        if f == "ler_conversa":
            return {"messages": self.msgs}
        if f == "encerrar_conversa":
            self.encerradas.append(a["conversaId"])
        return {}

class FakeEJC:
    def chamar(self, f, **a):
        if f == "get_pessoa":
            return {"data": {"celular": ""}}
        if a.get("id_responsavel_qualquer") == d.LUCAS["id"]:
            return {"data": [{"id": 1, "cliente": 9, "nome_cliente": "Mateus Ferreira", "data": "2026-10-05",
                              "hora_fim": "15:00", "status": "C", "descricao": "Revisão de contrato"}]}
        return {"data": []}

def rodar(z):
    d._concluidos.update(ultima=None, feitos=set())
    d.DRY_RUN = False
    c = {"encerradas": 0}
    d.encerrar_concluidos(z, lambda: FakeEJC(), datetime(2026, 10, 6, 15, 30, tzinfo=d.BRT), c)
    return c["encerradas"]

antes = [{"sender": "USER", "content": "link do Meet", "createdAt": "2026-10-05T17:27:00.000Z"}]
z = FakeZ(antes); assert rodar(z) == 1 and z.encerradas == ["c1"]
z = FakeZ(antes, status="CLOSED"); assert rodar(z) == 0
esperando = antes + [{"sender": "CONTACT", "content": "e o contrato?", "createdAt": "2026-10-06T12:00:00.000Z"}]
z = FakeZ(esperando); assert rodar(z) == 0 and not z.encerradas, "cliente esperando resposta"
print("OK — concluído no EasyJur encerra a conversa")

# ---- mensagem de advogado citando o horário não é confirmação nem muda o advogado (caso de 07/10)
r4 = "*Dra Danielle Esteves*:\n*Dr. Lucas:*\nOlá, Helena! Aqui é o Dr. Lucas. Confirmo nosso atendimento de hoje, quarta-feira, 07/10, às 12h30"
assert not r4.startswith("*Annie*")
assert d.advogado_do_texto(r4) is d.LUCAS
assert d.advogado_do_texto("*Annie*:\nOlá! O Dr. Lucas analisou o seu caso") is d.LUCAS
assert d.advogado_do_texto("*Annie*:\nA Dra. Danielle Esteves analisou") is d.DANIELLE
print("OK — assinatura não confunde o advogado")

# ---- orçamento do EasyJur: trava por plantão e pausa após cota esgotada (15/10)
from datetime import timedelta
d.ESTADO_EJ.update(chamadas=0, pausado_ate=None, avisado=False, recentes=[])
limite_original = d.EASYJUR_MAX_PLANTAO
d.EASYJUR_MAX_PLANTAO = 3
for _ in range(3):
    d._registrar_chamada_easyjur()
try:
    d._registrar_chamada_easyjur()
    assert False, "deveria recusar a 4ª chamada"
except d.OrcamentoEasyJur as e:
    assert "limite de 3" in str(e)
assert d.ESTADO_EJ["chamadas"] == 3
d.ESTADO_EJ.update(chamadas=0, recentes=[], pausado_ate=datetime.now(d.BRT) + timedelta(minutes=30))
try:
    d._registrar_chamada_easyjur()
    assert False, "deveria estar em pausa"
except d.OrcamentoEasyJur as e:
    assert "pausa" in str(e)
d.ESTADO_EJ.update(chamadas=0, recentes=[], pausado_ate=datetime.now(d.BRT) - timedelta(minutes=1))
d._registrar_chamada_easyjur()  # pausa vencida: volta a chamar
d.EASYJUR_MAX_PLANTAO = limite_original

# o aviso de erro sai uma vez só por plantão, vai só ao privado do Dr. Lucas e nunca derruba a rodada
class FakeZAviso:
    def __init__(self): self.enviadas = []
    def chamar(self, f, **a):
        self.enviadas.append((f, a.get("numero") or a.get("grupoId"))); return {}
d.ESTADO_EJ.update(avisado=False)
d.DRY_RUN = False
z = FakeZAviso()
d._avisar_orcamento(z, d.OrcamentoEasyJur("limite de 60 chamadas ao EasyJur neste plantão atingido"))
d._avisar_orcamento(z, d.OrcamentoEasyJur("de novo"))
assert z.enviadas == [("enviar_mensagem", d.TEL_ERROS)], z.enviadas
assert d.ja_avisou_lucas(z, ("EasyJur pausado",))
assert not d.ja_avisou_lucas(z, ("NÃO CONSEGUI GRAVAR", "5594900000001"))
print("OK — orçamento do EasyJur (aviso só ao Dr. Lucas)")

# ---- limite por hora: com o limite da hora estourado, recusa; quando a janela passa, volta
d.ESTADO_EJ.update(chamadas=0, pausado_ate=None, recentes=[datetime.now(d.BRT) - timedelta(minutes=5)] * d.EASYJUR_MAX_HORA)
try:
    d._registrar_chamada_easyjur()
    assert False, "deveria recusar pelo limite da hora"
except d.OrcamentoEasyJur as e:
    assert "por hora" in str(e)
d.ESTADO_EJ.update(recentes=[datetime.now(d.BRT) - timedelta(minutes=61)] * d.EASYJUR_MAX_HORA)
d._registrar_chamada_easyjur()
d.ESTADO_EJ.update(chamadas=0, recentes=[])
print("OK — limite do EasyJur por hora")

# ---- pergunta repetida da Annie não é confirmação (caso Hana, 18/10)
ofert = {("19", "10", "09", "30"), ("19", "10", "14", "30")}
pergunta = ("*Annie*: Então me diga só qual horário fica melhor pra você: segunda-feira, 19/10, às 09h30 "
            "ou às 14h30?")
assert not d.e_confirmacao(pergunta, ofert)
assert not d.e_confirmacao("*Annie*: Tenho 19/10, às 09h30 e 14h30 livres.", ofert)
assert d.e_confirmacao("*Annie*: Perfeito, Hana! Ficou marcado para segunda-feira, 19/10, às 14h30, "
                       "por videochamada.", ofert)
assert d.e_confirmacao("*Annie*: Combinado! O atendimento será na segunda-feira, 19/10, às 09h30.", ofert)
print("OK — confirmação só quando a Annie fecha um horário")

# ---- lead pedindo outro horário é detectado; escolher um da oferta não é (caso Hana, 18/10)
ofert = {("19", "10", "09", "30"), ("19", "10", "14", "30")}
assert d.pediu_outro_horario("Nesses horários estou trabalhando fica muito puxado \nTeria o horário de 13h?", ofert)
assert d.pediu_outro_horario("Não consigo nesse dia, pode ser quarta?", ofert)
assert not d.pediu_outro_horario("Pode ser às 14h30", ofert)
assert not d.pediu_outro_horario("O primeiro", ofert)
assert not d.pediu_outro_horario("Está sim", ofert)
print("OK — pedido de outro horário detectado")

# ---- GRAVAR pelo grupo e lembretes (8h do dia + 1h antes)
from datetime import timezone as _tz
assert d.ler_gravar("GRAVAR Hana 19/10 13h")[:5] == ("Hana", 19, 10, 13, 0)
assert d.ler_gravar("gravar Hana Souza 19/10 às 13:30 com Fernanda")[:5] == ("Hana Souza", 19, 10, 13, 30)
assert d.ler_gravar("vamos gravar o vídeo amanhã") is None
assert d.advogado_por_nome("com Fernanda") is d.FERNANDA


class ZG:
    def __init__(s): s.env = []
    def chamar(s, f, **a):
        s.env.append((f, a))
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": "c1", "contact": {"id": "k1", "name": "Hana"}}}
        if f == "ler_conversa":
            return {"messages": [{"sender": "USER", "createdAt": "2026-10-18T11:29:06.000Z", "content":
                                  "*Annie*:\nOlá, Hana! A Dra. Fernanda Mesquita analisou o seu caso e pode te atender "
                                  "por videochamada. Tenho estes horários: 1) segunda-feira, 19/10, às 09h30; 2) "
                                  "segunda-feira, 19/10, às 14h30. Qual fica melhor pra você?"}]}
        return {}


class EJG:
    def __init__(s): s.env = []
    def chamar(s, f, **a):
        s.env.append((f, a))
        if f == "list_pessoas":
            return {"data": []}
        if f in ("create_pessoa", "create_oportunidade", "create_agenda"):
            return {"data": {"id": 77}}
        if f == "list_agenda":
            return {"data": [], "meta": {"total_pages": 1}}
        return {"data": {}}


agora_g = datetime(2026, 10, 18, 18, 30, tzinfo=_tz.utc)
z, ej = ZG(), EJG()
d.DRY_RUN = False
d._gravadas.clear(); d._falhas.clear()
grupos = {d.GRUPO: [{"id": "claude-mensagem-99001", "sender": "CONTACT", "senderName": "Fernanda Mesquita",
                     "content": "GRAVAR Hana 19/10 13h", "createdAt": "2026-10-18T18:20:00.000Z"}]}
leads_g = [{"nome": "Hana", "tel": "5594900000001", "texto": "Família"}]
d.gravar_pelo_grupo(z, d.Conversas(z), lambda: ej, lambda: d.Agenda(ej, agora_g.astimezone(d.BRT)), leads_g, [],
                    agora_g, {"reunioes": 0}, grupos)
ag = [a for f, a in ej.env if f == "create_agenda"][0]
assert (ag["id_advogado"], ag["data"], ag["hora_inicio"]) == (378457, "2026-10-19", "13:00")
lemb = [a["dataHora"] for f, a in z.env if f == "agendar_mensagem"]
assert lemb == ["2026-10-19T11:00:00.000Z", "2026-10-19T15:00:00.000Z"], lemb  # 8h e 12h de Belém
aviso = [a["texto"] for f, a in z.env if f == "enviar_mensagem_grupo"][0]
assert "REUNIÃO AGENDADA" in aviso and "#99001" in aviso and "8h, 1h antes" in aviso
# rodada seguinte, com o aviso já no grupo: não grava de novo
grupos[d.GRUPO].append({"id": "x", "sender": "AGENT", "content": aviso, "createdAt": "2026-10-18T18:31:00.000Z"})
z2, ej2 = ZG(), EJG()
d.gravar_pelo_grupo(z2, d.Conversas(z2), lambda: ej2, lambda: d.Agenda(ej2, agora_g.astimezone(d.BRT)), leads_g, [],
                    agora_g, {"reunioes": 0}, grupos)
assert not [f for f, a in ej2.env if f.startswith("create")]
print("OK — GRAVAR pelo grupo e lembretes 8h + 1h")

# reunião às 09h30: só o lembrete de 1 hora antes (não manda dois seguidos de manhã)
z3 = ZG()
r = d.lembretes(z3, "k", "c", "Ana", d.FERNANDA, datetime(2026, 10, 19, 9, 30, tzinfo=d.BRT),
                datetime(2026, 10, 18, 15, 0, tzinfo=d.BRT))
assert r == ["1h antes"]
print("OK — reunião cedo: só lembrete de 1 hora antes")

# ---- equipe combinou 13h e o lead aceitou: sugere GRAVAR no grupo (caso Hana)
from datetime import timedelta as _td
_now = datetime.now(_tz.utc)
_iso = lambda m: (_now - _td(minutes=m)).isoformat().replace("+00:00", "Z")
of_msg = {"sender": "USER", "createdAt": _iso(300), "content": "*Annie*:\nOlá, Hana! Tenho estes horários: 1) segunda-feira, 19/10, às 09h30; 2) segunda-feira, 19/10, às 14h30. Qual fica melhor pra você?"}
hist = [of_msg,
        {"sender": "CONTACT", "createdAt": _iso(298), "content": "Nesses horários estou trabalhando. Teria 13h?"},
        {"sender": "AGENT", "createdAt": _iso(100), "content": "*Annie*: ela consegue sim lhe atender as 13hs ☺️"}]
z = ZG(); d._sugestao_gravar.clear()
of = set(d.RE_SLOT.findall(of_msg["content"]))
d.sugerir_gravar(z, {"contact": {"name": "Hana"}}, {"tel": "5594900000001", "nome": "Hana"}, hist, of_msg, of, {"mensagens": []}, {})
assert not z.env, "sem aceite do lead ainda: não sugere"
hist.append({"sender": "CONTACT", "createdAt": _iso(5), "content": "Pode ser sim, obrigada"})
d.sugerir_gravar(z, {"contact": {"name": "Hana"}}, {"tel": "5594900000001", "nome": "Hana"}, hist, of_msg, of, {"mensagens": []}, {})
txt = z.env[0][1]["texto"]
assert "HORÁRIO COMBINADO" in txt and "GRAVAR Hana DD/MM 13h" in txt, txt
print("OK — sugestão de GRAVAR quando o lead aceita horário combinado")

# ---- Google Agenda pela ponte: link vai para o EasyJur, lembretes, cliente e advogado (simulado)
import agenda_google
agenda_google.criar_reuniao = lambda *a, **k: {"id": "ev1", "link": "https://meet.google.com/abc-defg-hij",
                                               "aberta": True, "ja_existia": False}


class ZM(ZG):
    def chamar(s, f, **a):
        if f == "listar_membros":
            s.env.append((f, a))
            return {"membros": [{"nome": "Automação", "email": "x@x"}, {"nome": "Fernanda Mesquita ", "email": "f@x"}]}
        return ZG.chamar(s, f, **a)


d._gravadas.clear(); d._falhas.clear(); d._emails.clear()
z, ej = ZM(), EJG()
grupos = {d.GRUPO: [{"id": "claude-mensagem-99002", "sender": "CONTACT", "senderName": "Fernanda Mesquita",
                     "content": "GRAVAR Hana 19/10 13h", "createdAt": "2026-10-18T18:20:00.000Z"}]}
d.gravar_pelo_grupo(z, d.Conversas(z), lambda: ej, lambda: d.Agenda(ej, agora_g.astimezone(d.BRT)), leads_g, [],
                    agora_g, {"reunioes": 0}, grupos)
ag = [a for f, a in ej.env if f == "create_agenda"][0]
assert "https://meet.google.com/abc-defg-hij" in ag["descricao"] and ag["local"].startswith("https://meet")
msgs_cli = [a["mensagem"] for f, a in z.env if f == "agendar_mensagem"]
assert len(msgs_cli) == 3 and all("meet.google.com/abc-defg-hij" in m for m in msgs_cli)  # 8h, 1h, confirmação
priv = [a for f, a in z.env if f == "enviar_mensagem"][0]
assert priv["numero"] == "5594991742534" and "REUNIÃO AGENDADA COM VOCÊ" in priv["texto"] and "meet.google" in priv["texto"]
assert d.email_do_advogado(z, d.FERNANDA) == "f@x" and d.email_do_advogado(z, d.DANIELLE) is None
print("OK — Google Agenda: link no EasyJur, lembretes, cliente e advogado")

# ---- cliente confirmou o lembrete de 1 hora antes: link vai para o advogado no privado
_n = datetime.now(_tz.utc)


class ZP(ZG):
    def __init__(s, msgs): super().__init__(); s.msgs = msgs
    def chamar(s, f, **a):
        s.env.append((f, a))
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": "c1", "contact": {"id": "k1", "name": "Hana"}}}
        if f == "ler_conversa":
            return {"messages": s.msgs}
        return {}


hist = [{"sender": "USER", "createdAt": (_n - _td(minutes=40)).isoformat().replace("+00:00", "Z"),
         "content": "*Annie*:\nOlá, Hana! Passando para confirmar nosso atendimento de hoje às 13h00 com a Dra. "
                    "Fernanda Mesquita. O link da videochamada é: https://meet.google.com/abc-defg-hij — é só clicar."},
        {"sender": "CONTACT", "createdAt": (_n - _td(minutes=35)).isoformat().replace("+00:00", "Z"),
         "content": "Sim, confirmo!"}]
d._presenca_avisada.clear()
zp = ZP(hist)
d.avisar_presenca(zp, d.Conversas(zp), [{"nome": "Hana", "tel": "5594900000001"}], {"mensagens": []}, _n, {})
envios = [a for f, a in zp.env if f == "enviar_mensagem"]
assert envios and envios[0]["numero"] == "5594991742534" and "meet.google.com/abc-defg-hij" in envios[0]["texto"]
zp2 = ZP(hist)
d.avisar_presenca(zp2, d.Conversas(zp2), [{"nome": "Hana", "tel": "5594900000001"}], {"mensagens": []}, _n, {})
assert not [f for f, a in zp2.env if f == "enviar_mensagem"]
print("OK — presença confirmada: link ao advogado uma vez")

# ---- celular no formato que o EasyJur aceita (o cru "55..." dava HTTP 422)
assert d.celular_br("5594900000001") == "(94) 90000-0001"
assert d.celular_br("559432221111") == "(94) 3222-1111"
assert d.celular_br("94900000001") == "(94) 90000-0001"
print("OK — celular no formato do EasyJur")
