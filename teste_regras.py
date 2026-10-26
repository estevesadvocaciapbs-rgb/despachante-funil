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
    item(344269, "2026-10-05", "ATENDIMENTO", "16:30", "17:00"),   # ocupa seg 16h30
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
assert not any(s.strftime("%d/%m %H:%M") == "05/10 16:30" for s in liv_d), "16h30 de segunda ocupado"
# grade da Dra. Danielle (26/10): só 10h30, 14h30, 15h30 e 16h30 — nunca outro horário
assert {s.strftime("%H:%M") for s in liv_d} <= {"10:30", "14:30", "15:30", "16:30"}
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
assert {"10:30", "15:30"} <= {s.strftime("%H:%M") for s in liv_f}  # incluídos em 23/10

seg_cedo = d.Agenda(FakeEJ([]), datetime(2026, 10, 5, 7, 0, tzinfo=d.BRT))  # segunda 7h
dois_seg = d.manha_e_tarde(seg_cedo.livres(d.DANIELLE, set()))
print("lead de segunda 7h ->", [d.texto_slot(s) for s in dois_seg])
assert [s.strftime("%d/%m %H:%M") for s in dois_seg] == ["06/10 10:30", "06/10 14:30"], \
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
# caso de 23/10: cliente já atendido pela Thalyta (lembrete de acordo); a Annie respondeu sem pergunta → não retoma
cliente_antigo = [
    {"sender": "USER", "senderName": "Thalyta Pereira Freitas", "content": "*Thalyta*:\n⚖️ LEMBRETE DE VENCIMENTO – ACORDO",
     "createdAt": "2026-10-03T00:10:00.000Z"},
    {"sender": "CONTACT", "content": "So segunda", "createdAt": "2026-10-03T00:14:57.000Z"},
    {"sender": "AGENT", "content": "*Annie*:\nSem problemas, o vencimento é na segunda. Quando fizer o pagamento, é só me "
     "encaminhar o comprovante por aqui, por favor.", "createdAt": "2026-10-03T00:15:48.003Z"}]
assert not d.precisa_retomar(cliente_antigo, AGR)
sem_thalyta = cliente_antigo[1:2] + [{"sender": "AGENT", "content": "*Annie*:\nCerto, anotado.",
                                      "createdAt": "2026-10-03T00:15:48.003Z"}]
assert d.precisa_retomar(sem_thalyta, AGR)  # sem equipe na conversa, a triagem travada continua sendo retomada
assert not d.precisa_retomar(sem_thalyta[:1] + [{"sender": "AGENT", "senderName": "", "content": "*Thalyta:* Olá!",
                                                 "createdAt": "2026-10-02T12:00:00.000Z"}] + sem_thalyta[1:], AGR)
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

# ---- salário-maternidade de empregada com carteira: só orientação, sem oferta de horário
_t = ("🆕 NOVO LEAD · Previdenciário — Maria Teste\nℹ️ DÚVIDA INFORMATIVA — SEM AGENDAMENTO\n"
      "CONTATO: Maria Teste (5594900000009)\nÁREA: Previdenciário — salário-maternidade")
assert d.classificar(_t) == (None, "informativo")
assert d.classificar("‼️NOVA OPORTUNIDADE‼️\nÁREA: Previdenciário — salário-maternidade")[0] == "previdenciario"
print("OK — dúvida informativa não recebe oferta")

# ---- a Za.Ia passou a exigir "assinatura" no enviar_mensagem (20/10/2026) e no enviar_mensagem_grupo
# (21/10/2026, a rodada inteira falhava no aviso de reunião gravada): nenhum envio sem ela
import re as _re, io as _io
for _arq in ("despachante.py", "secretaria.py", "retorno.py", "porteiro.py"):
    _src = _io.open(_arq, encoding="utf-8").read()
    _sem = [l for l in _src.splitlines()
            if _re.search(r'"enviar_mensagem(_grupo)?"', l) and "assinatura=" not in l]
    assert not _sem, (_arq, _sem)
print("OK — todo enviar_mensagem e enviar_mensagem_grupo leva assinatura")

# ---- lead escolhe o horário e a Annie não confirma (caso Júnior 21/10: conversa transferida ao advogado)
from datetime import timezone as _tz2, timedelta as _td2
_oferta_txt = ("*Annie*:\nOlá, Júnior! O Dr. Lucas analisou o seu caso e pode te atender por videochamada. "
               "Tenho estes horários: 1) quinta-feira, 22/10, às 10h30; 2) quinta-feira, 22/10, às 14h00. "
               "Qual fica melhor pra você?")
_slots = list(dict.fromkeys(d.RE_SLOT.findall(_oferta_txt)))
for _t, _esp in [("Amanhã às 10h30", ("22", "10", "10", "30")), ("14h", ("22", "10", "14", "00")),
                 ("pode ser 10:30", ("22", "10", "10", "30")), ("O primeiro", ("22", "10", "10", "30")),
                 ("2", ("22", "10", "14", "00")), ("de manhã", ("22", "10", "10", "30")),
                 ("não posso às 10h30", None), ("10h30 ou 14h tanto faz", None), ("Isso mesmo", None),
                 ("teria 16h?", None), ("Amanhã", None)]:
    assert d.slot_escolhido(_t, _slots) == _esp, (_t, d.slot_escolhido(_t, _slots))

def _m(sender, texto, quando):
    return {"sender": sender, "content": texto, "createdAt": quando}
_oferta = _m("USER", _oferta_txt, "2026-10-21T12:53:02.508Z")
_msgs = [_oferta, _m("CONTACT", "Isso mesmo", "2026-10-21T12:53:37.000Z"),
         _m("AGENT", "*Annie*:\nPerfeito, Júnior! Então me diga só qual horário fica melhor: quinta-feira, 22/10, "
                     "às 10h30, ou às 14h00?", "2026-10-21T12:54:28.774Z"),
         _m("CONTACT", "Amanhã às 10h30", "2026-10-21T12:54:54.000Z")]
_t0 = datetime(2026, 10, 21, 12, 57, tzinfo=_tz2.utc)
assert d.escolha_do_lead(_msgs, _oferta, _oferta_txt, _t0) is None             # ainda dentro dos 5 min
_esc = d.escolha_do_lead(_msgs, _oferta, _oferta_txt, _t0 + _td2(minutes=5))
assert _esc and _esc[1] == ("22", "10", "10", "30")
# a Annie respondeu depois da escolha: o fluxo normal cuida
assert d.escolha_do_lead(_msgs + [_m("AGENT", "*Annie*:\nok", "2026-10-21T12:55:10.000Z")], _oferta, _oferta_txt,
                         _t0 + _td2(minutes=5)) is None
# o lead voltou atrás
assert d.escolha_do_lead(_msgs + [_m("CONTACT", "não, melhor à tarde", "2026-10-21T12:56:10.000Z")], _oferta,
                         _oferta_txt, _t0 + _td2(minutes=9)) is None
# já confirmado pelo despachante: não manda de novo
_ini = d.data_do_texto("22", "10", "10", "30", _t0)
_conf = _m("USER", f"*Annie*:\nPerfeito, Júnior! Seu atendimento {d.MARCA_CONFIRMACAO} {d.texto_slot(_ini)}, por "
                   "videochamada com Dr. Lucas.", "2026-10-21T13:00:00.000Z")
assert not d.ja_confirmado_ao_lead(_msgs, _msgs[-1], _ini) and d.ja_confirmado_ao_lead(_msgs + [_conf], _msgs[-1], _ini)
print("OK — lead escolheu e a Annie não confirmou: o despachante confirma uma vez")

# --- 23/10: oferta em lista ("• quinta-feira, 22/10 às 10:30") ---
_d1 = datetime(2026, 10, 22, 10, 30, tzinfo=d.BRT)
_d2 = datetime(2026, 10, 22, 14, 0, tzinfo=d.BRT)
_lista = d.texto_da_oferta("Júnior", d.LUCAS, [_d1, _d2])
assert d.MARCA_OFERTA in _lista and "• quinta-feira, 22/10 às 10:30\n• quinta-feira, 22/10 às 14:00" in _lista, _lista
assert _lista.endswith("\n\nQual fica melhor pra você?")
_sl = list(dict.fromkeys(d.RE_SLOT.findall(_lista)))
assert _sl == [("22", "10", "10", "30"), ("22", "10", "14", "00")], _sl
# o lead escolhe pela hora, pelo turno ou pela ordem da lista
for _t, _esp in [("10:30", _sl[0]), ("às 14h", _sl[1]), ("o primeiro", _sl[0]), ("de tarde", _sl[1]),
                 ("22/10 às 14:00", _sl[1]), ("pode ser 16h?", None)]:
    assert d.slot_escolhido(_t, _sl) == _esp, (_t, d.slot_escolhido(_t, _sl))
# a Annie confirma copiando o horário da lista (com dois-pontos) ou no formato antigo
_of = set(_sl)
assert d.e_confirmacao("Perfeito, Júnior! Seu atendimento ficou marcado para quinta-feira, 22/10 às 14:00, por videochamada.", _of)
assert d.e_confirmacao("Perfeito! Ficou marcado para quinta-feira, 22/10, às 14h00.", _of)
assert not d.e_confirmacao("Qual fica melhor: 22/10 às 10:30 ou 22/10 às 14:00?", _of)
_om = _m("USER", "*Annie*:\n" + _lista, "2026-10-21T12:53:02.508Z")
_res = d.reservas_recentes([_om], datetime(2026, 10, 21, 10, 0, tzinfo=d.BRT))
assert (d.LUCAS["id"], _d1) in _res and (d.LUCAS["id"], _d2) in _res, _res
_cm = _m("USER", "*Annie*:\nPerfeito! Seu atendimento ficou marcado para quinta-feira, 22/10 às 10:30.", "2026-10-21T13:10:00.000Z")
assert d.ja_confirmado_ao_lead([_om, _cm], _om, _d1) and not d.ja_confirmado_ao_lead([_om, _cm], _om, _d2)
print("OK — oferta em lista: lida, escolhida e confirmada como a antiga")

# --- 23/10: lead pede atendimento presencial depois da oferta (a conversa não pode parar) ---
_listaF = d.texto_da_oferta("Júnior", d.FERNANDA, [_d1, _d2])
for _t, _esp in [("Gostaria de atendimento presencial", "presencial"), ("Prefiro ir pessoalmente", "presencial"),
                 ("posso ir no escritório?", "presencial"), ("não posso online, só presencial", "presencial"),
                 ("não precisa ser presencial", "online"), ("pode ser por vídeo mesmo", "online"),
                 ("pode ser online", "online"), ("14h", None), ("ok", None)]:
    assert d.pede_presencial(_t) == _esp, (_t, d.pede_presencial(_t))
_o1 = _m("USER", "*Annie*:\n" + _listaF, "2026-10-21T12:53:02.508Z")
_p1 = _m("CONTACT", "Gostaria que fosse presencial", "2026-10-21T12:55:00.000Z")
_an = _m("AGENT", "*Annie*:\nVou verificar com a equipe e já te retorno.", "2026-10-21T12:55:20.000Z")
assert d.modo_da_conversa([_o1], _o1["createdAt"]) == "online"
assert d.modo_da_conversa([_o1, _p1], _o1["createdAt"]) == "presencial"
assert d.modo_da_conversa([_o1, _p1, _m("CONTACT", "pensando bem, pode ser online", "2026-10-21T12:58:00.000Z")],
                          _o1["createdAt"]) == "online"


class ZP:
    def __init__(s): s.env = []
    def chamar(s, f, **a):
        s.env.append((f, a))
        return {}


_conv = {"id": "c9", "contact": {"id": "k9", "name": "Júnior Teste"}}
_lead = {"nome": "Júnior Teste", "tel": "5594900000009", "texto": ""}
_t1 = datetime(2026, 10, 21, 12, 56, tzinfo=_tz2.utc)
d.DRY_RUN = False
d._presencial_oferecido.clear()
_z = ZP()
# dentro dos 3 minutos: espera a Annie (mas segura o aviso de "outro horário")
assert d.oferecer_presencial(_z, _conv, _lead, [_o1, _p1, _an], _o1, _listaF, _t1, {}) and not _z.env
# 3 minutos sem a Annie repetir os horários: repete os MESMOS horários, presencial
assert d.oferecer_presencial(_z, _conv, _lead, [_o1, _p1, _an], _o1, _listaF, _t1 + _td2(minutes=3), {})
_rep = [a["mensagem"] for f, a in _z.env if f == "agendar_mensagem"]
assert len(_rep) == 1 and d.MARCA_PRESENCIAL in _rep[0] and d.MARCA_OFERTA in _rep[0], _rep
assert "• quinta-feira, 22/10 às 10:30\n• quinta-feira, 22/10 às 14:00" in _rep[0] and "Dra. Fernanda" in _rep[0]
assert [a.get("ativarIaAoResponder") for f, a in _z.env] == [True]
# rodada seguinte (mensagem ainda agendada): não repete
assert d.oferecer_presencial(_z, _conv, _lead, [_o1, _p1, _an], _o1, _listaF, _t1 + _td2(minutes=4), {})
assert len([f for f, a in _z.env if f == "agendar_mensagem"]) == 1
# a repetição já está na conversa: segue o fluxo normal; e a escolha seguinte é presencial
_r1 = _m("USER", "*Annie*:\n" + _rep[0], "2026-10-21T13:00:00.000Z")
_ch = _m("CONTACT", "às 14h", "2026-10-21T13:01:00.000Z")
_conv_msgs = [_o1, _p1, _an, _r1, _ch]
assert not d.oferecer_presencial(_z, _conv, _lead, _conv_msgs, _o1, _listaF, _t1 + _td2(minutes=10), {})
_ofs = [x for x in _conv_msgs if d.MARCA_OFERTA in x["content"]]
assert d.modo_da_conversa(_conv_msgs, d.inicio_do_ciclo(_ofs)) == "presencial"
assert d.escolha_do_lead(_conv_msgs, _ofs[-1], _ofs[-1]["content"], _t1 + _td2(minutes=11))[1] == _sl[1]
# alguém da equipe respondeu: não se mete
d._presencial_oferecido.clear()
_eq = _m("AGENT", "*Thalyta:* Vou ver com a Dra. e te falo", "2026-10-21T12:56:00.000Z")
assert not d.oferecer_presencial(ZP(), _conv, _lead, [_o1, _p1, _eq], _o1, _listaF, _t1 + _td2(minutes=5), {})
# a Annie já repetiu os horários: não repete de novo
_ar = _m("AGENT", "*Annie*:\nClaro! Pode ser presencial: 22/10 às 10:30 ou 22/10 às 14:00?", "2026-10-21T12:55:30.000Z")
assert not d.oferecer_presencial(ZP(), _conv, _lead, [_o1, _p1, _ar], _o1, _listaF, _t1 + _td2(minutes=5), {})
print("OK — pedido presencial: mesmos horários repetidos, sem parar a conversa")

# gravação presencial: local no escritório, nenhum link ao cliente, lembretes dizem "aqui no escritório"
_zg, _ejg = ZP(), EJG()
d._gravadas.clear(); d._falhas.clear()
assert d.gravar_reuniao(_zg, _ejg, _conv, "Júnior Teste", _lead["tel"], d.FERNANDA, _d2, "civel", "caso", [],
                        datetime(2026, 10, 21, 9, 0, tzinfo=d.BRT), {"reunioes": 0}, ("t", "x"), "teste",
                        modo="presencial")
_ag = [a for f, a in _ejg.env if f == "create_agenda"][0]
assert _ag["local"] == "Presencial — escritório" and "PRESENCIAL" in _ag["descricao"]
_txts = [a["mensagem"] for f, a in _zg.env if f == "agendar_mensagem"]
assert len(_txts) == 3 and all("videochamada" not in t and "meet." not in t for t in _txts), _txts
assert all("no escritório" in t for t in _txts) and d.MARCA_LEMBRETE_1H in _txts[1]
assert "Presencial (escritório)" in [a["texto"] for f, a in _zg.env if f == "enviar_mensagem_grupo"][0]
assert "vem ao escritório" in [a["texto"] for f, a in _zg.env if f == "enviar_mensagem"][0]
print("OK — reunião presencial gravada sem link e com lembretes do escritório")

# caso de 19/10: "Tem atendimento presencial" -> Annie manda o endereço -> "Pode ser 9.30 presencial" e
# ninguém confirma. O despachante confirma em 5 min, e a reunião é presencial.
_ofA = ("*Annie*:\nOlá, Fulano! A Dra. Fernanda Mesquita analisou o seu caso e pode te atender por videochamada. "
        "Tenho estes horários: 1) terça-feira, 20/10, às 09h30; 2) terça-feira, 20/10, às 14h30. Qual fica melhor pra você?")
_slA = list(dict.fromkeys(d.RE_SLOT.findall(_ofA)))
assert d.slot_escolhido("Pode ser 9.30 presencial", _slA) == ("20", "10", "09", "30")
assert d.slot_escolhido("R$ 1.500", _slA) is None
_mA = [_m("USER", _ofA, "2026-10-19T17:40:00.000Z"), _m("CONTACT", "Tem aténdimento presencial", "2026-10-19T17:41:00.000Z"),
       _m("AGENT", "*Annie*:\nTemos sim! O endereço é ... Qual horário fica melhor?", "2026-10-19T17:42:00.000Z"),
       _m("CONTACT", "Pode ser 9.30 presencial", "2026-10-19T17:44:00.000Z"),
       _m("CONTACT", "vai ser cobrado algo pela consulta?", "2026-10-19T17:45:00.000Z")]
_eA = d.escolha_do_lead(_mA, _mA[0], _ofA, datetime(2026, 10, 19, 17, 50, tzinfo=_tz2.utc))
assert _eA and _eA[1] == ("20", "10", "09", "30")
assert d.modo_da_conversa(_mA, d.inicio_do_ciclo([_mA[0]])) == "presencial"
print("OK — caso de 19/10: '9.30 presencial' vira reunião presencial confirmada")

# --- 23/10: Dr. Lucas só atende online. Lead dele que pede presencial recebe os horários da Dra. Danielle.
class AgDani:
    def __init__(s, livres): s.l = livres; s.pedidos = []
    def livres(s, adv, reservados):
        s.pedidos.append(adv["id"])
        return [x for x in s.l if (adv["id"], x) not in reservados]


_dn1 = datetime(2026, 10, 26, 10, 0, tzinfo=d.BRT)
_dn2 = datetime(2026, 10, 26, 14, 30, tzinfo=d.BRT)
_ag = AgDani([_dn1, _dn2])
_oL = _m("USER", "*Annie*:\n" + _lista, "2026-10-21T12:53:02.508Z")   # oferta do Dr. Lucas (videochamada)
_pL = _m("CONTACT", "Pode ser 14h presencial?", "2026-10-21T12:55:00.000Z")
_aL = _m("AGENT", "*Annie*:\nO Dr. Lucas atende só por videochamada, mas a Dra. Danielle pode te atender aqui no "
                  "escritório. Já te mando os horários dela, tá bom?", "2026-10-21T12:55:20.000Z")
d._presencial_oferecido.clear()
_z = ZP()
_t2 = datetime(2026, 10, 21, 12, 55, 40, tzinfo=_tz2.utc)
assert d.oferecer_presencial(_z, _conv, _lead, [_oL, _pL, _aL], _oL, _lista, _t2, {}, lambda: _ag, set) and not _z.env
assert d.oferecer_presencial(_z, _conv, _lead, [_oL, _pL, _aL], _oL, _lista, _t2 + _td2(minutes=1), {},
                             lambda: _ag, set)
_tx = [a["mensagem"] for f, a in _z.env if f == "agendar_mensagem"]
assert len(_tx) == 1 and "Dr. Lucas atende só por videochamada" in _tx[0] and "a Dra. Danielle Esteves" in _tx[0], _tx
assert "• segunda-feira, 26/10 às 10:00\n• segunda-feira, 26/10 às 14:30" in _tx[0] and "22/10" not in _tx[0], _tx
assert d.advogado_do_texto(_tx[0]) is d.DANIELLE and _ag.pedidos == [d.DANIELLE["id"]]
assert "PRESENCIAL COM A DRA. DANIELLE" in [a["texto"] for f, a in _z.env if f == "enviar_mensagem_grupo"][0]
# a escolha seguinte é presencial com a Dra. Danielle (a nova oferta passa a ser a dela)
_rL = _m("USER", "*Annie*:\n" + _tx[0], "2026-10-21T12:57:00.000Z")
_msL = [_oL, _pL, _aL, _rL, _m("CONTACT", "14:30", "2026-10-21T12:58:00.000Z")]
_ofL = [x for x in _msL if d.MARCA_OFERTA in x["content"]]
assert d.modo_da_conversa(_msL, d.inicio_do_ciclo(_ofL)) == "presencial"
assert d.escolha_do_lead(_msL, _ofL[-1], _ofL[-1]["content"], _t2 + _td2(minutes=9))[1] == ("26", "10", "14", "30")
# sem horário da Dra. Danielle: avisa o grupo, uma vez
d._presencial_oferecido.clear()
_z2 = ZP()
assert d.oferecer_presencial(_z2, _conv, _lead, [_oL, _pL], _oL, _lista, _t2 + _td2(minutes=2), {},
                             lambda: AgDani([]), set)
assert not [f for f, a in _z2.env if f == "agendar_mensagem"]
assert "PRESENCIAL SEM HORÁRIO" in [a["texto"] for f, a in _z2.env if f == "enviar_mensagem_grupo"][0]
# confirmar() nunca confirma presencial com o Dr. Lucas, mesmo que o lead escolha um horário dele
class ConvF:
    def __init__(s, conv, msgs): s.c = (conv, msgs)
    def de(s, tel): return s.c
d._presencial_oferecido.clear()
_z3, _ej3 = ZP(), EJG()
_msE = [_oL, _m("CONTACT", "às 14h, presencial", "2026-10-21T12:55:00.000Z")]
d.confirmar(_z3, ConvF(_conv, _msE), lambda: _ej3, lambda: _ag, [_lead], [], _t2 + _td2(minutes=10), {"reunioes": 0})
assert not [f for f, a in _ej3.env if f.startswith("create")]
assert not [a for f, a in _z3.env if f == "enviar_mensagem" and "ficou marcado" in a.get("texto", "")]
assert "Dra. Danielle" in [a["mensagem"] for f, a in _z3.env if f == "agendar_mensagem"][0]
print("OK — Dr. Lucas só online: pedido presencial vai para a Dra. Danielle")

# --- 23/10: lead não aceitou a oferta. Outro horário → mais 2 horários; exceção/sem horário → privado do advogado
_ofs = {("22", "10", "10", "30"), ("22", "10", "14", "00")}
for _t, _esp in [(["não posso nesses"], "outro"), (["teria às 16h?"], "outro"), (["pode ser na quarta?"], None),
                 (["Boa noite! Não consigo nesses horários"], "outro"), (["só consigo à noite"], "excecao"),
                 (["teria 13h?"], "excecao"), (["pode ser sábado?"], "excecao"), (["só depois das 18h"], "excecao"),
                 (["essa semana não dá, estou viajando"], "sem_horario"), (["estou sem tempo, depois eu vejo"], "sem_horario"),
                 (["ok, obrigado"], None)]:
    assert d.tipo_de_recusa(_t, _ofs) == _esp, (_t, d.tipo_de_recusa(_t, _ofs))

_ag0 = datetime(2026, 10, 21, 9, 0, tzinfo=d.BRT)
_liv = [datetime(2026, 10, 22, h, m, tzinfo=d.BRT) for h, m in ((10, 30), (11, 0), (14, 0), (16, 0))] + \
       [datetime(2026, 10, 26, h, m, tzinfo=d.BRT) for h, m in ((10, 0), (15, 0))]
_ja = {_liv[0], _liv[2]}
assert d.escolher_outros(_liv, _ja, "não posso nesses", _ag0) == ([_liv[1], _liv[3]], True)
assert d.escolher_outros(_liv, _ja, "teria às 16h?", _ag0)[0][0] == _liv[3]
assert d.escolher_outros(_liv, _ja, "pode ser na segunda à tarde?", _ag0) == ([_liv[5]], True)
assert d.escolher_outros(_liv, _ja, "semana que vem", _ag0) == ([_liv[4], _liv[5]], True)
_s, _ok = d.escolher_outros(_liv, _ja, "na sexta", _ag0)  # sexta não tem atendimento: oferece os próximos
assert _s and not _ok


class AgLivre:
    def __init__(s, livres, itens=()): s.l = livres; s.i = list(itens)
    def livres(s, adv, reservados): return [x for x in s.l if (adv["id"], x) not in reservados]
    def itens(s, adv_id, a, b, tipo=None): return s.i


class ConvL:
    def __init__(s, m): s.m = m
    def de(s, tel): return s.m.get(tel, (None, []))


_lista2 = d.texto_da_oferta("Júnior", d.FERNANDA, [_d1, _d2])
_o = _m("USER", "*Annie*:\n" + _lista2, "2026-10-21T12:00:00.000Z")
_pede = _m("CONTACT", "não posso nesses, teria mais tarde?", "2026-10-21T12:02:00.000Z")
_ann = _m("AGENT", "*Annie*:\nSem problema! Já te mando outras opções por aqui, tá bom?", "2026-10-21T12:02:20.000Z")
_agL = AgLivre([_d1, _d2, datetime(2026, 10, 22, 15, 30, tzinfo=d.BRT), datetime(2026, 10, 22, 16, 30, tzinfo=d.BRT)])
_tA = datetime(2026, 10, 21, 12, 2, 30, tzinfo=_tz2.utc)
d._reofertas.clear(); d._avisos_advogado.clear()
_z = ZP()
_cv = ConvL({})
d.outros_horarios(_z, _cv, _conv, _lead, [_o, _pede, _ann], [_o], lambda: _agL, set, _tA, {})
assert not _z.env  # espera 1 minuto (a Annie responde primeiro)
d.outros_horarios(_z, _cv, _conv, _lead, [_o, _pede, _ann], [_o], lambda: _agL, set, _tA + _td2(minutes=1), {})
_r = [a["mensagem"] for f, a in _z.env if f == "agendar_mensagem"]
assert len(_r) == 1 and d.MARCA_MAIS in _r[0] and d.MARCA_OFERTA in _r[0], _r
assert "22/10 às 15:30" in _r[0] and "22/10 às 16:30" in _r[0] and "14:00" not in _r[0], _r
assert not [f for f, a in _z.env if f.startswith("enviar_mensagem")]  # nada no grupo
# a nova oferta vale como oferta: escolha, confirmação e reserva seguem o fluxo normal
_o2 = _m("USER", "*Annie*:\n" + _r[0], "2026-10-21T12:04:00.000Z")
assert d.escolha_do_lead([_o, _pede, _ann, _o2, _m("CONTACT", "16:30", "2026-10-21T12:05:00.000Z")], _o2, _o2["content"],
                         _tA + _td2(minutes=9))[1] == ("22", "10", "16", "30")
# depois de 2 novas ofertas recusadas, o advogado é avisado no privado
_o3 = _m("USER", "*Annie*:\nSem problema! A Dra. Fernanda Mesquita pode te atender por videochamada "
                 f"{d.MARCA_MAIS}. {d.MARCA_OFERTA}:\n\n• segunda-feira, 26/10 às 10:00\n\nQual fica melhor pra você?",
         "2026-10-21T12:10:00.000Z")
_rec = [_o, _pede, _ann, _o2, _m("CONTACT", "também não dá", "2026-10-21T12:06:00.000Z"), _o3,
        _m("CONTACT", "não consigo nesses também", "2026-10-21T12:11:00.000Z")]
_z = ZP()
d.outros_horarios(_z, _cv, _conv, _lead, _rec, [_o, _o2, _o3], lambda: _agL, set, _tA + _td2(minutes=14), {})
_pv = [a for f, a in _z.env if f == "enviar_mensagem"]
assert len(_pv) == 1 and _pv[0]["numero"] == d.FERNANDA["tel"] and "NÃO ACEITOU AS OFERTAS" in _pv[0]["texto"], _pv
assert "OFERECER Júnior" in _pv[0]["texto"] and "GRAVAR Júnior" in _pv[0]["texto"]
assert not [f for f, a in _z.env if f == "agendar_mensagem"]
# exceção de horário: espera o lead terminar (5 min) e avisa o advogado no privado, com os horários livres dele
d._avisos_advogado.clear()
_exc = [_o, _m("CONTACT", "Trabalho o dia todo, só consigo à noite ou sábado", "2026-10-21T12:02:00.000Z")]
_z = ZP()
d.outros_horarios(_z, _cv, _conv, _lead, _exc, [_o], lambda: _agL, set, _tA + _td2(minutes=2), {})
assert not _z.env
d.outros_horarios(_z, _cv, _conv, _lead, _exc, [_o], lambda: _agL, set, _tA + _td2(minutes=5), {})
_pv = [a for f, a in _z.env if f == "enviar_mensagem"]
assert len(_pv) == 1 and "EXCEÇÃO DE HORÁRIO" in _pv[0]["texto"] and "só consigo à noite" in _pv[0]["texto"]
assert "15h30" in _pv[0]["texto"] and not [f for f, a in _z.env if f == "enviar_mensagem_grupo"]
d.outros_horarios(_z, _cv, _conv, _lead, _exc, [_o], lambda: _agL, set, _tA + _td2(minutes=9), {})
assert len([f for f, a in _z.env if f == "enviar_mensagem"]) == 1  # uma vez só
print("OK — outro horário: mais 2 horários; exceção e sem horário: aviso no privado do advogado")

# OFERECER e GRAVAR no privado do advogado com o escritório
assert d.ler_oferecer("OFERECER Ana 28/10 19h e 29/10 12h30")[1] == [(28, 10, 19, 0), (29, 10, 12, 30)]
assert d.ler_oferecer("oferecer Ana Souza 28/10 às 19:00 ou 20h")[1] == [(28, 10, 19, 0), (28, 10, 20, 0)]
assert d.ler_oferecer("vou oferecer café") is None


class ZPriv(ZP):
    def chamar(s, f, **a):
        s.env.append((f, a))
        if f == "buscar_contatos":
            return {"contatos": []}
        return {}


_leadA = {"nome": "Júnior Teste", "tel": "5594900000009", "texto": "Família"}
_cvA = ConvL({"5594900000009": (_conv, [_o])})
_agora_p = datetime(2026, 10, 21, 15, 0, tzinfo=_tz2.utc)
_priv = {d.FERNANDA["tel"]: [_m("CONTACT", "OFERECER Júnior 28/10 19h e 29/10 12h30", "2026-10-21T14:58:00.000Z")]}
_zp = ZPriv()
d.comandos_dos_advogados(_zp, _cvA, lambda: EJG(), lambda: AgLivre([]), [_leadA], [], _agora_p, {}, {}, _priv)
_to_lead = [a["mensagem"] for f, a in _zp.env if f == "agendar_mensagem"]
assert len(_to_lead) == 1 and d.MARCA_ESPECIAL in _to_lead[0] and "Fernanda" in _to_lead[0], _to_lead
assert "28/10 às 19:00" in _to_lead[0] and "29/10 às 12:30" in _to_lead[0]
_resp = [a for f, a in _zp.env if f == "enviar_mensagem"]
assert _resp and _resp[0]["numero"] == d.FERNANDA["tel"] and "Ofereci" in _resp[0]["texto"]
# rodada seguinte com a resposta já no privado: não repete
_priv[d.FERNANDA["tel"]].append(_m("USER", _resp[0]["texto"], "2026-10-21T14:59:00.000Z"))
_zp2 = ZPriv()
d.comandos_dos_advogados(_zp2, _cvA, lambda: EJG(), lambda: AgLivre([]), [_leadA], [], _agora_p, {}, {}, _priv)
assert not _zp2.env
# horário especial ocupado: não envia
_ocup = [{"tipo": "AUDIENCIA", "status": "A", "hora_inicio": "18:30:00", "hora_fim": "19:30:00"}]
_zp3 = ZPriv()
d.comandos_dos_advogados(_zp3, _cvA, lambda: EJG(), lambda: AgLivre([], _ocup), [_leadA], [], _agora_p, {}, {},
                         {d.FERNANDA["tel"]: [_m("CONTACT", "OFERECER Júnior 28/10 19h", "2026-10-21T14:58:30.000Z")]})
assert not [f for f, a in _zp3.env if f == "agendar_mensagem"]
assert "já tem compromisso" in [a["texto"] for f, a in _zp3.env if f == "enviar_mensagem"][0]
# GRAVAR no privado: grava com o advogado dono do privado e responde lá
d._gravadas.clear(); d._falhas.clear()
_zp4, _ej4 = ZPriv(), EJG()
d.comandos_dos_advogados(_zp4, _cvA, lambda: _ej4, lambda: d.Agenda(_ej4, _agora_p.astimezone(d.BRT)), [_leadA], [],
                         _agora_p, {"reunioes": 0}, {},
                         {d.DANIELLE["tel"]: [_m("CONTACT", "GRAVAR Júnior 28/10 19h", "2026-10-21T14:58:40.000Z")]})
_agd = [a for f, a in _ej4.env if f == "create_agenda"][0]
assert (_agd["id_advogado"], _agd["data"], _agd["hora_inicio"]) == (d.DANIELLE["id"], "2026-10-28", "19:00")
assert "Gravado" in [a["texto"] for f, a in _zp4.env if f == "enviar_mensagem" and a["numero"] == d.DANIELLE["tel"]][-1]
# mensagem de cliente no privado de outro número não vale como comando
_zp5 = ZPriv()
d.comandos_dos_advogados(_zp5, _cvA, lambda: EJG(), lambda: AgLivre([]), [_leadA], [], _agora_p, {}, {},
                         {"5594900000077": [_m("CONTACT", "OFERECER Júnior 28/10 19h", "2026-10-21T14:58:00.000Z")]})
assert not _zp5.env
print("OK — OFERECER e GRAVAR no privado do advogado com o escritório")

# o lead escolhe o horário especial (19h, fora da grade): grava sem acusar conflito de agenda
_esp_txt = _to_lead[0]
_oe = _m("USER", "*Annie*:\n" + _esp_txt, "2026-10-21T15:01:00.000Z")
_ce = _m("AGENT", "*Annie*:\nPerfeito, Júnior! Seu atendimento com a Dra. Fernanda ficou marcado para quarta-feira, "
                  "28/10, às 19h00, por videochamada.", "2026-10-21T15:03:00.000Z")
d._gravadas.clear(); d._falhas.clear()
_z6, _ej6 = ZP(), EJG()
d.confirmar(_z6, ConvF(_conv, [_o, _oe, _m("CONTACT", "19h", "2026-10-21T15:02:00.000Z"), _ce]), lambda: _ej6,
            lambda: AgLivre([]), [_leadA], [], datetime(2026, 10, 21, 15, 10, tzinfo=_tz2.utc),
            {"reunioes": 0, "conflitos": 0})
_ag6 = [a for f, a in _ej6.env if f == "create_agenda"]
assert _ag6 and _ag6[0]["hora_inicio"] == "19:00" and _ag6[0]["id_advogado"] == d.FERNANDA["id"], _ag6
assert not [a for f, a in _z6.env if f == "enviar_mensagem_grupo" and "CONFLITO" in a["texto"]]
print("OK — horário especial do advogado é gravado sem acusar conflito")

# ---- 26/10 (caso Thiago): Dra. Danielle sem horário → Dr. Lucas (trabalhista e previdenciário); nunca outro horário
class AgPor:
    def __init__(s, por_adv): s.p = por_adv
    def livres(s, adv, reservados): return list(s.p.get(adv["id"], []))
    def itens(s, *a, **k): return []


_hL = datetime(2026, 10, 27, 14, 0, tzinfo=d.BRT)
for _area in ("Trabalhista — Rescisão Indireta", "Previdenciário — aposentadoria"):
    _leadT = {"nome": "Teste Lead", "tel": "5594900000031", "quando": datetime(2026, 10, 26, 12, 0, tzinfo=_tz2.utc),
              "texto": f"‼️NOVA OPORTUNIDADE‼️\nÁREA: {_area}\nResumo: caso de teste com salário atrasado, assédio grave e "
                       "provas documentais; trabalhou 3 anos na empresa com carteira assinada."}
    _zT = ZP()
    _cvT = ConvL({"5594900000031": ({"id": "c31", "contact": {"id": "k31", "name": "Teste Lead"}}, [])})
    d.ofertar(_zT, _cvT, lambda: AgPor({d.DANIELLE["id"]: [], d.LUCAS["id"]: [_hL]}), [_leadT],
              datetime(2026, 10, 26, 12, 30, tzinfo=_tz2.utc), {"ofertas": 0, "pulados": 0, "sem_horario": 0},
              {"mensagens": [{"sender": "CONTACT", "senderName": "Danielle Esteves", "content": "AGENDAR Teste",
                              "createdAt": "2026-10-26T12:20:00.000Z"}]})
    _of = [a["mensagem"] for f, a in _zT.env if f == "agendar_mensagem"]
    assert _of and "Dr. Lucas" in _of[0] and "Fernanda" not in _of[0], (_area, _of)
    _zT = ZP()
    d.ofertar(_zT, _cvT, lambda: AgPor({d.DANIELLE["id"]: [_hL], d.LUCAS["id"]: [_hL]}), [_leadT],
              datetime(2026, 10, 26, 12, 30, tzinfo=_tz2.utc), {"ofertas": 0, "pulados": 0, "sem_horario": 0},
              {"mensagens": [{"sender": "CONTACT", "senderName": "Danielle Esteves", "content": "AGENDAR Teste",
                              "createdAt": "2026-10-26T12:20:00.000Z"}]})
    assert "Danielle" in [a["mensagem"] for f, a in _zT.env if f == "agendar_mensagem"][0]
print("OK — Dra. Danielle sem horário: vai para o Dr. Lucas (trabalhista e previdenciário)")

# ---- 26/10: GRAVAR não grava por cima de outro compromisso do advogado
d._gravadas.clear(); d._falhas.clear()
_ocup2 = [{"tipo": "PARTICULAR", "status": "A", "hora_inicio": "18:30:00", "hora_fim": "19:30:00",
           "data": "2026-10-28", "data_fim": "2026-10-28"}]
_zp9, _ej9 = ZPriv(), EJG()
d.comandos_dos_advogados(_zp9, _cvA, lambda: _ej9, lambda: AgLivre([], _ocup2), [_leadA], [], _agora_p, {"reunioes": 0},
                         {}, {d.DANIELLE["tel"]: [_m("CONTACT", "GRAVAR Júnior 28/10 19h", "2026-10-21T14:58:50.000Z")]})
assert not [a for f, a in _ej9.env if f == "create_agenda"]
assert "já tem compromisso" in [a["texto"] for f, a in _zp9.env if f == "enviar_mensagem"][-1]
print("OK — GRAVAR recusa horário que já tem compromisso")
