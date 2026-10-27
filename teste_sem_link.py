"""Teste da reunião gravada à mão sem link e do lead novo vindo do Suporte (dados inventados; não acessa nada)."""
import os
from datetime import datetime, timezone

os.environ.setdefault("TELEFONES_EQUIPE", "5594992048054,5594991742534,5524992432455")
import despachante as d
import reuniao_sem_link as r
import agenda_google

UTC = timezone.utc
AGORA = datetime(2026, 10, 27, 12, 20, tzinfo=UTC)  # 9h20 em Belém
d.DRY_RUN = False
agenda_google.criar_reuniao = lambda *a, **k: {"link": "https://meet.google.com/aaa-bbbb-ccc"}


def item(**kw):
    base = {"id": 900, "tipo": "ATENDIMENTO", "status": "A", "data": "2026-10-27", "data_cadastro": "2026-10-26",
            "hora_inicio": "14:30", "local": "Online", "descricao": "Relato do caso.", "id_advogado": d.DANIELLE["id"],
            "id_advogado2": 354290, "cliente": 77, "nome_cliente": "Fulana"}
    base.update(kw)
    return base


class EJ:
    def __init__(s, itens, celular="(94) 99000-0001"):
        s.env, s.itens, s.cel = [], itens, celular

    def chamar(s, f, **k):
        s.env.append((f, k))
        if f == "list_agenda":
            return {"data": s.itens}
        if f == "get_pessoa":
            return {"data": {"celular": s.cel}}
        return {}


class Z:
    def __init__(s, msgs=()):
        s.env, s.msgs = [], list(msgs)

    def chamar(s, f, **k):
        s.env.append((f, k))
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": "v1", "contact": {"id": "c1", "name": "Fulana"}}}
        if f == "ler_conversa":
            return {"messages": s.msgs}
        if f == "ler_grupo":
            return {"mensagens": []}
        if f == "buscar_contatos":
            return {"contatos": []}
        return {}


def rodar(itens, msgs=(), **kw):
    r._estado.update(ultima=None, avisados=set())
    ej, z = EJ(itens, **kw), Z(msgs)
    r.rodada(z, lambda: ej, d.Conversas(z), AGORA, {}, d)
    return ej, z


# reunião online sem link: Meet criado, EasyJur atualizado, link ao cliente, lembrete de 1 h e aviso ao advogado
ej, z = rodar([item()])
assert [k for f, k in ej.env if f == "update_agenda"][0]["local"] == "https://meet.google.com/aaa-bbbb-ccc"
ag = [k for f, k in z.env if f == "agendar_mensagem"]
assert len(ag) == 2 and "meet.google.com/aaa" in ag[0]["mensagem"] and ag[0]["assinatura"] == "ia"
assert any(k["numero"] == d.DANIELLE["tel"] and r.TITULO in k["texto"] for f, k in z.env if f == "enviar_mensagem")
assert [k for f, k in z.env if f == "buscar_conversa_por_telefone"][0]["telefone"] == "5594990000001"
# já tem link, é presencial, está cancelada, começa já, não tem hora: nada
for it in (item(local="https://meet.google.com/x"), item(local="Presencial — escritório"), item(status="S"),
           item(hora_inicio="09:30"), item(hora_inicio="00:00"), item(tipo="TAREFA")):
    ej, z = rodar([it])
    assert not [f for f, k in ej.env if f == "update_agenda"] and not [f for f, k in z.env if f == "agendar_mensagem"]
# a equipe já mandou um link na conversa: só copia para o EasyJur, sem mensagem ao cliente
msg = {"sender": "USER", "content": "*Thalyta*:\nLink: https://meet.google.com/zzz-yyyy-xxx",
       "createdAt": "2026-10-27T11:00:00.000Z"}
ej, z = rodar([item()], [msg])
assert [k for f, k in ej.env if f == "update_agenda"][0]["local"].endswith("zzz-yyyy-xxx")
assert not [f for f, k in z.env if f == "agendar_mensagem"]
# sem cliente vinculado nem telefone: aviso no grupo, uma vez
ej, z = rodar([item(cliente=0, nome_cliente="")])
av = [k for f, k in z.env if f == "enviar_mensagem_grupo"]
assert len(av) == 1 and r.SEM_TEL in av[0]["texto"] and "#A900" in av[0]["texto"]

# lead novo que a Annie tratou no Suporte (caso Vera): vira lead; cliente antigo ou com equipe atendendo, não
TAREFA = {"title": "Fulana — Trabalhista: rescisão indireta por assédio - Fulana", "createdAt": "2026-10-27T12:16:03.000Z",
          "description": "Relato.\n\nDepartamento: suporte\nContato: Fulana (5571990000002)"}


class ZS(Z):
    def __init__(s, criado, msgs=(), etiquetas=()):
        super().__init__(msgs)
        s.criado, s.etq = criado, [{"name": e} for e in etiquetas]

    def chamar(s, f, **k):
        if f == "buscar_contatos":
            return {"contatos": [{"phone": "5571990000002", "createdAt": s.criado, "labels": s.etq}]}
        return super().chamar(f, **k)


agora = datetime(2026, 10, 27, 12, 30, tzinfo=UTC)
d._contatos.clear()
z = ZS("2026-10-27T11:52:12.000Z", [{"sender": "CONTACT", "content": "oi", "createdAt": "2026-10-27T11:52:00.000Z"}])
novos = d.leads_de_suporte(z, d.Conversas(z), [TAREFA], agora, set())
assert len(novos) == 1 and d.classificar(novos[0]["texto"]) == ("trabalhista", None)
for zz in (ZS("2026-06-01T10:00:00.000Z"), ZS("2026-10-27T11:52:12.000Z", etiquetas=["Cliente"]),
           ZS("2026-10-27T11:52:12.000Z", [{"sender": "USER", "senderName": "Thalyta Pereira Freitas",
                                           "content": "*Thalyta*:\nOi!", "createdAt": "2026-10-27T12:00:00.000Z"}])):
    d._contatos.clear()
    assert d.leads_de_suporte(zz, d.Conversas(zz), [TAREFA], agora, set()) == []
d._contatos.clear()
assert d.leads_de_suporte(z, d.Conversas(z), [dict(TAREFA, title="Fulana — envio de documentos")], agora, set()) == []
print("OK — reunião gravada à mão sem link (Meet + link ao cliente) e lead novo vindo do Suporte")
