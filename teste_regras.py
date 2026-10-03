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
