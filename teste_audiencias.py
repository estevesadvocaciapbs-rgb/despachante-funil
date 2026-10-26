"""Teste do cadastro de audiência designada em publicação (dados inventados; não acessa nenhum sistema)."""
import os
from datetime import date, datetime, timezone

os.environ.setdefault("TELEFONES_EQUIPE", "5594992048054,5594991742534,5524992432455")
import despachante as d
import audiencias as a

HOJE = date(2026, 10, 26)
T1 = ("Intimação. Fica a parte intimada de que designo audiência UNA a ser realizada em 29/10/2026 08:30, na "
      "modalidade telepresencial. Link de acesso pelo navegador: https://trt8-jus-br.zoom.us/j/88990000000?pwd=abc "
      "ID da reunião: 889 9000 0000 senha de acesso: xyz")
T2 = ("Redesigno a audiência de instrução para o dia 10 de novembro de 2026, às 09h30, a ser realizada pelo Teams: "
      "https://teams.microsoft.com/l/meetup-join/xyz")
T3 = "Audiência realizada em 20/10/2026 às 10:00. Partes conciliaram. Prazo de 5 dias para manifestação."
T4 = "Designo audiência de conciliação. A data será informada oportunamente."
T5 = ("Designo audiência de conciliação para 11/11/2026 às 10:00. Caso infrutífera, fica desde já designada a "
      "audiência de instrução para 25/11/2026 às 14:00.")

assert a.achar_audiencias(T1, HOJE) == [(date(2026, 10, 29), "08:30", "una")], a.achar_audiencias(T1, HOJE)
# formato real do TRT8 (nomes fictícios): não usa a palavra "audiência"
T6 = ("Publicacao Processo: 0000001-00.2026.5.08.0000 Data de disponibilizacao: 20-10-2026 Tipo de comunicacao: "
      "Intimacao ... DESPACHO Considerando a essencia conciliatoria da Justica do Trabalho, determino: 1. Inclusao em "
      "pauta do dia 22/10/2026 09:00 para tentativa de conciliacao, TELE PRESENCIALMENTE, pelo aplicativo ZOOM, com acesso "
      "pelo link abaixo: Entrar na reuniao Zoom https://trt8-jus-br.zoom.us/j/80000000000?pwd=abc ID da reuniao: 800 0000 "
      "0000 Senha de acesso: abc 2. Partes cientes. PARAUAPEBAS/PA, 19 de outubro de 2026. FULANO Juiz do Trabalho")
assert [(x[0], x[1]) for x in a.achar_audiencias(T6, date(2026, 10, 20))] == [(date(2026, 10, 22), "09:00")]
assert a.tem_designacao(T6) and "zoom.us" in a.link_da_sala(T6)
assert [(x[0], x[1]) for x in a.achar_audiencias(T2, HOJE)] == [(date(2026, 11, 10), "09:30")]
assert a.achar_audiencias(T3, HOJE) == [] and not a.tem_designacao(T3)
assert a.achar_audiencias(T4, HOJE) == [] and a.tem_designacao(T4)
assert len(a.achar_audiencias(T5, HOJE)) == 2
assert a.link_da_sala(T1).startswith("https://trt8-jus-br.zoom.us/") and "teams" in a.link_da_sala(T2)


class EJ:
    def __init__(s, texto, agenda_pub=(), agenda_proc=()):
        s.env, s.t, s.ap, s.pr = [], texto, list(agenda_pub), list(agenda_proc)

    def chamar(s, f, **k):
        s.env.append((f, k))
        if f == "list_publicacoes":
            return {"data": [{"id": 1, "codPublicacao": "999", "numProcesso": "0000001-00.2026.5.08.0000",
                              "dataDisponibilizacao": "2026-10-26"}] if k["idNome"] == "26088398" else []}
        if f == "get_publicacao":
            return {"data": {"codPublicacao": "999", "conteudoPublicacao": s.t, "numProcesso": "0000001-00.2026.5.08.0000",
                             "processo": {"id": 77}}}
        if f == "list_agenda":
            return {"data": s.ap if "cod_publicacao" in k else s.pr}
        if f == "create_agenda":
            return {"data": {"id": 5555}}
        return {}


class Z:
    def __init__(s): s.env = []

    def chamar(s, f, **k):
        s.env.append((f, k))
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": "p1"}}
        if f == "ler_conversa":
            return {"messages": []}
        return {}


AGORA = datetime(2026, 10, 26, 13, 0, tzinfo=timezone.utc)  # 10h em Belém
d.DRY_RUN = False


def rodar(texto, **kw):
    a._estado.update(ultima=None, vistos=set())
    ej, z = EJ(texto, **kw), Z()
    a.rodada(z, lambda: ej, AGORA, {}, d)
    return ej, z


ej, z = rodar(T1)
ag = [k for f, k in ej.env if f == "create_agenda"]
assert len(ag) == 1 and ag[0]["tipo"] == "AUDIENCIA" and ag[0]["data"] == "2026-10-29" and ag[0]["hora_inicio"] == "08:30"
assert ag[0]["id_advogado"] == d.FERNANDA["id"] and ag[0]["processo"] == 77 and ag[0]["codigo_publicacao"] == "999"
assert "zoom.us" in ag[0]["local"] and "meet.google" not in ag[0]["local"]
av = [k for f, k in z.env if f == "enviar_mensagem"]
assert av and av[0]["numero"] == d.FERNANDA["tel"] and a.TITULO in av[0]["texto"] and "nº 5555" in av[0]["texto"]
assert "29/10/2026 às 08h30" in av[0]["texto"] and "P-999" in av[0]["texto"]
# já tem agenda ligada à publicação, ou audiência do processo nesse dia: não cadastra nem avisa
for kw in ({"agenda_pub": [{"id": 1}]}, {"agenda_proc": [{"id": 2, "status": "A"}]}):
    ej, z = rodar(T1, **kw)
    assert not [f for f, k in ej.env if f == "create_agenda"] and not [f for f, k in z.env if f == "enviar_mensagem"]
# data ambígua ou ilegível: não cadastra, só avisa para conferir
for t in (T4, T5):
    ej, z = rodar(t)
    assert not [f for f, k in ej.env if f == "create_agenda"]
    assert "confira" in [k for f, k in z.env if f == "enviar_mensagem"][0]["texto"]
# audiência passada ou publicação sem designação: nada
for t in (T3, "Intimação para manifestar sobre o laudo em 5 dias."):
    ej, z = rodar(t)
    assert not [f for f, k in ej.env if f == "create_agenda"] and not [f for f, k in z.env if f == "enviar_mensagem"]
print("OK — audiência designada em publicação: agenda do EasyJur com o link do tribunal e alerta ao advogado")
