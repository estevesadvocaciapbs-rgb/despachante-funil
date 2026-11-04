"""Testes da limpeza das tarefas (dados fictícios; casos de 03/11 e 04/11)."""
import tarefas_limpas as tl
import despachante as d

BRIEF = ("‼️ NOVA OPORTUNIDADE ‼️\nLEAD: Ana Teste (11999990000)\nÁREA: Trabalhista\n\n"
         "Trabalhou 3 anos sem registro, salário atrasado.")
VAZOU = (BRIEF + "\n\nResumo do atendimento:\n1) RELEITURA: a cliente disse...\n2) HISTÓRICO: ...\n"
         "6) AVANÇO: concluir. Tom do cliente: ANSIOSO\n\nContexto:\nDecisão: transferir porque...\n\n"
         "Dados coletados:\nsalario_atrasado: sim\n\nDepartamento: comercial\n\nContato: Ana Teste (11999990000)")

limpa = tl.sem_raciocinio(VAZOU)
assert "RELEITURA" not in limpa and "Decisão" not in limpa and "HISTÓRICO" not in limpa, limpa
assert "Trabalhou 3 anos" in limpa and "Dados coletados:" in limpa and "Departamento: comercial" in limpa
assert "Contato: Ana Teste" in limpa and "Tom do cliente: ANSIOSO" in limpa
assert tl.sem_raciocinio(limpa) == limpa, "precisa ser idempotente"
assert tl.sem_raciocinio(BRIEF) == BRIEF
# o despachante continua lendo o briefing do mesmo jeito
assert d.resumo_do_caso(limpa) == d.resumo_do_caso(VAZOU)
assert d.avaliar_trabalhista(limpa, d.datetime.now(d.BRT)) == d.avaliar_trabalhista(VAZOU, d.datetime.now(d.BRT))
print("OK — tarefa sem o raciocínio da IA, briefing lido igual (caso de 03/11)")


class Z:
    def __init__(self):
        self.env = []

    def chamar(self, f, **a):
        self.env.append((f, a))
        return {}


def tarefa(i, criada, desc, titulo="🆕 NOVO LEAD — Trabalhista", contato="contato-1", feita=None):
    return {"id": f"tarefa-{i}", "title": titulo, "description": desc, "createdAt": criada,
            "completedAt": feita, "contatoId": contato}


tarefas = [tarefa(1, "2026-11-04T11:00:00.000Z", VAZOU),
           tarefa(2, "2026-11-04T11:20:00.000Z", BRIEF + "\n\nMandou áudio: tem as conversas de WhatsApp com o gerente."),
           tarefa(3, "2026-11-04T11:40:00.000Z", BRIEF),
           tarefa(4, "2026-11-04T12:00:00.000Z", BRIEF, contato="contato-2"),
           tarefa(5, "2026-11-04T12:10:00.000Z", BRIEF, contato="contato-2", feita="2026-11-04T12:30:00.000Z"),
           tarefa(6, "2026-11-04T12:20:00.000Z", "Ligar para o fórum", titulo="Pendência", contato="contato-1")]
z, cont, logs = Z(), {}, []
tl.rodada(z, tarefas, cont, logs.append)
feitas = [a["tarefaId"] for f, a in z.env if f == "completar_tarefa"]
assert feitas == ["tarefa-2", "tarefa-3"], feitas
titulos = {a["tarefaId"]: a["campos"]["titulo"] for f, a in z.env if f == "atualizar_tarefa" and "titulo" in a["campos"]}
assert titulos["tarefa-2"].startswith("DUPLICADA (ver tarefa-1)"), titulos
orig = [a["campos"]["descricao"] for f, a in z.env if f == "atualizar_tarefa" and a["tarefaId"] == "tarefa-1"]
assert "RELEITURA" not in orig[0] and "conversas de WhatsApp com o gerente" in orig[-1], orig
assert orig[-1].count("NOVA OPORTUNIDADE") == 1 and orig[-1].count("Trabalhou 3 anos") == 1, orig[-1]
assert not any(a.get("tarefaId") in ("tarefa-4", "tarefa-5", "tarefa-6") for f, a in z.env), z.env
assert "Ana" not in " ".join(logs) and "1199" not in " ".join(logs), logs
# segunda rodada: nada a fazer
z2 = Z()
tl.rodada(z2, [t for t in tarefas if t["id"] not in ("tarefa-2", "tarefa-3")], {}, logs.append)
assert z2.env == [], z2.env
# simulação não grava nada
z3 = Z()
tl.rodada(z3, [tarefa(7, "2026-11-04T11:00:00.000Z", VAZOU), tarefa(8, "2026-11-04T11:10:00.000Z", BRIEF)], {}, logs.append, True)
assert z3.env == [], z3.env
print("OK — briefing repetido do mesmo lead vai para a primeira tarefa e a repetida é concluída (caso de 04/11)")

# dados coletados: só o trecho acrescentado entra na atualização
_o = BRIEF + "\n\nDados coletados:\ndetalhe_problema: trabalha 3 anos.\nsalario: 2 mil"
_r = BRIEF + "\n\nDados coletados:\ndetalhe_problema: trabalha 3 anos. Acrescenta: tem prints.\nsalario: 2 mil\nprova: prints"
_n = tl.novidades(_o, _r)
assert _n == "detalhe_problema: Acrescenta: tem prints.\n\nprova: prints", _n
assert tl.novidades(_o, _o) == ""
print("OK — atualização da tarefa leva só o que é novo nos dados coletados")
