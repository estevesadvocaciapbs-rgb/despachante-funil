"""Testes da faxina das conversas resolvidas (05/11). Dados fictícios."""
from datetime import datetime, timedelta, timezone
import despachante as d
import faxina as f

agora = datetime(2026, 11, 5, 20, 0, tzinfo=timezone.utc)
def m(sender, txt, horas_atras):
    return {"sender": sender, "content": txt, "createdAt": (agora - timedelta(hours=horas_atras)).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
FIN = {"claude-etiqueta-5"}
# frases de encerramento
for t in ("Obrigada!", "ok", "Muito obrigado, doutora", "👍🙏", "Tá bom, obrigada pela atenção", "Certo, boa tarde!", "já resolvi"):
    assert f.encerra_assunto(t, d), t
for t in ("Bom dia", "Obrigada, e o processo?", "ok, mas quando sai o dinheiro", "Bom dia, preciso falar com a Dra. sobre meu caso", ""):
    assert not f.encerra_assunto(t, d), t
# Finalizado + escritório respondeu por último: resolvida
assert f.resolvida([m("CONTACT", "Quando é a audiência?", 30), m("AGENT", "*Thalyta:* Dia 10 às 9h", 29)], FIN, agora, d)
# Finalizado mas cliente mandou pergunta nova: fica
assert not f.resolvida([m("AGENT", "*Thalyta:* Dia 10 às 9h", 29), m("CONTACT", "E precisa levar testemunha?", 5)], FIN, agora, d)
# Finalizado, cliente perguntou e só a Annie respondeu: fica
assert not f.resolvida([m("CONTACT", "E precisa levar testemunha?", 5), m("AGENT", "*Annie*:\nVou verificar com a Dra.", 4)], FIN, agora, d)
# sem Finalizado: cliente agradeceu por último: resolvida
assert f.resolvida([m("AGENT", "*Dra. Danielle:* Já protocolei", 6), m("CONTACT", "Obrigada doutora!", 5)], set(), agora, d)
# sem Finalizado: agradeceu, escritório perguntou algo depois: fica (bola com o cliente)
assert not f.resolvida([m("CONTACT", "Obrigada", 6), m("AGENT", "*Thalyta:* Pode mandar o RG?", 5)], set(), agora, d)
# conversa recente (menos de 2 h): fica
assert not f.resolvida([m("AGENT", "*Thalyta:* ok", 3), m("CONTACT", "Obrigada", 1)], FIN, agora, d)
# arquivo sem texto do cliente: fica
assert not f.resolvida([m("AGENT", "*Thalyta:* ok", 30), m("CONTACT", None, 20)], FIN, agora, d)
print("OK — regras da faxina")

class Z:
    def __init__(s): s.env = []
    def chamar(s, ferr, **a):
        s.env.append((ferr, a))
        if ferr == "listar_contatos":
            if a["etiqueta"] == "PENDÊNCIA LUCAS":
                return {"contatos": [{"id": "c1", "phone": "5594900000001", "labels": [{"id": "claude-etiqueta-13"}, {"id": "claude-etiqueta-5"}]},
                                     {"id": "c2", "phone": "5594900000002", "labels": [{"id": "claude-etiqueta-13"}]},
                                     {"id": "c3", "phone": "5594900000003", "labels": [{"id": "claude-etiqueta-13"}]}], "total": 3}
            return {"contatos": [], "total": 0}
        if ferr == "listar_conversas":
            return {"conversas": []}
        if ferr == "buscar_conversa_por_telefone":
            n = a["telefone"][-1]
            return {"conversa": {"id": "conv" + n, "status": "CLOSED" if n == "3" else "OPEN"}}
        if ferr == "ler_conversa":
            if a["conversaId"] == "conv1":
                return {"messages": [m("CONTACT", "Obrigado", 30)]}
            return {"messages": [m("CONTACT", "Doutor, saiu a sentença?", 30)]}
        return {}
d.DRY_RUN = False
z = Z()
f._estado["hora"] = None
f.rodada(z, datetime(2026, 11, 5, 20, 5, tzinfo=timezone.utc), {}, d)  # 17h05 em Belém
fechou = [a["conversaId"] for x, a in z.env if x == "encerrar_conversa"]
tirou = [a["contatoId"] for x, a in z.env if x == "remover_etiqueta_contato"]
assert fechou == ["conv1"], fechou          # c2 perguntou e ninguém respondeu: fica aberta
assert sorted(tirou) == ["c1", "c3"], tirou  # c3: conversa já encerrada pela equipe perde a etiqueta
# mesma hora: não repete
z.env.clear(); f.rodada(z, datetime(2026, 11, 5, 20, 30, tzinfo=timezone.utc), {}, d)
assert not z.env
# contato com lembrete agendado não é tocado
f._estado["hora"] = None; z.env.clear()
f.rodada(z, datetime(2026, 11, 5, 20, 5, tzinfo=timezone.utc), {}, d, pendentes=[{"contactId": "c1"}])
assert "c1" not in [a["contatoId"] for x, a in z.env if x == "remover_etiqueta_contato"]
print("OK — faxina encerra só o resolvido e tira a pendência do Dr. Lucas")
