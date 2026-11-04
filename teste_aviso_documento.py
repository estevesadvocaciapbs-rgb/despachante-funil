"""Testes do aviso de documento de cliente (dados fictícios; caso de 04/11)."""
from datetime import datetime, timezone

import aviso_documento as ad
import despachante as d

AGORA = datetime(2026, 11, 4, 21, 0, tzinfo=timezone.utc)
CLI = "5500000000011"


def iso(h, mi):
    return datetime(2026, 11, 4, h, mi, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Z:
    def __init__(self, nome="Ana Cliente Fernanda", etiquetas=(), msgs=None, privado=()):
        self.env, self.nome, self.etiquetas = [], nome, etiquetas
        self.msgs = msgs if msgs is not None else [
            {"sender": "CONTACT", "contentType": "DOCUMENT", "content": "PRONTUARIO.pdf", "createdAt": iso(20, 40)},
            {"sender": "CONTACT", "contentType": "IMAGE", "content": "Foto de cartão de ponto", "createdAt": iso(20, 41)},
            {"sender": "CONTACT", "contentType": "CHAT", "content": "mandei", "createdAt": iso(20, 42)},
            {"sender": "AGENT", "contentType": "CHAT", "content": "*Annie*: recebi", "createdAt": iso(20, 43)}]
        self.privado = list(privado)

    def chamar(self, f, **a):
        self.env.append((f, a))
        if f == "listar_conversas":
            return {"atendimentos": [{"phone": CLI, "name": self.nome, "lastMessageAt": iso(20, 43),
                                      "conversa": {"id": "conv-1", "status": "OPEN"}}]}
        if f == "buscar_contatos":
            return {"contatos": [{"id": "c1", "name": self.nome, "phone": CLI,
                                  "labels": [{"name": e} for e in self.etiquetas]}]}
        if f == "ler_conversa":
            return {"messages": self.privado if a["conversaId"] == "priv" else self.msgs}
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": "priv"}}
        return {}


def zera():
    ad._estado["ultima"] = None
    ad._vistos.clear()
    ad._avisado.clear()


def enviados(z):
    return [a for f, a in z.env if f == "enviar_mensagem"]


# caso Wellington: cliente salvo "... Cliente Fernanda" manda PDF e foto -> um aviso só, no privado dela
zera(); z = Z(); cont = {}
ad.rodada(z, AGORA, cont, d, [])
e = enviados(z)
assert len(e) == 1 and e[0]["numero"] == d.FERNANDA["tel"] and e[0]["assinatura"] == "ia", e
assert ad.MARCA in e[0]["texto"] and "PRONTUARIO.pdf" in e[0]["texto"] and "Chegaram 2 arquivos" in e[0]["texto"], e
assert "mandei" not in e[0]["texto"]
# a mesma rajada não é avisada de novo (nem no mesmo plantão, nem em outro)
ad._estado["ultima"] = None
z2 = Z(); ad.rodada(z2, AGORA, {}, d, []); assert not enviados(z2)
zera(); z3 = Z(privado=[{"content": e[0]["texto"]}]); ad.rodada(z3, AGORA, {}, d, []); assert not enviados(z3)
# rajada ainda chegando (último arquivo há menos de 4 min): espera
zera(); z4 = Z(msgs=[{"sender": "CONTACT", "contentType": "IMAGE", "content": "foto", "createdAt": iso(20, 58)}])
ad.rodada(z4, AGORA, {}, d, []); assert not enviados(z4)
# lead (sem etiqueta Cliente, nome sem advogada) não gera aviso; lead "Pedro Lucas" também não
zera(); z5 = Z(nome="Pedro Silva"); ad.rodada(z5, AGORA, {}, d, []); assert not enviados(z5)
zera(); z6 = Z(nome="Pedro Lucas"); ad.rodada(z6, AGORA, {}, d, []); assert not enviados(z6)
# cliente sem advogada no nome: etiqueta PENDÊNCIA DANI -> Dra. Danielle; só "Cliente" -> Dra. Danielle
zera(); z7 = Z(nome="Pedro Silva", etiquetas=("Cliente", "PENDÊNCIA DANI")); ad.rodada(z7, AGORA, {}, d, [])
assert enviados(z7)[0]["numero"] == d.DANIELLE["tel"]
# cliente com tarefa aberta no nome do Dr. Lucas -> Dr. Lucas; tarefa de briefing de lead não conta
t = [{"contatoId": "c1", "completedAt": None, "assigneeId": "claude-usuario-2", "title": "Juntar CTPS", "description": ""}]
zera(); z8 = Z(nome="Pedro Silva", etiquetas=("Cliente",)); ad.rodada(z8, AGORA, {}, d, t)
assert enviados(z8)[0]["numero"] == d.LUCAS["tel"]
tb = [dict(t[0], title="🆕 NOVO LEAD · Trabalhista")]
zera(); z9 = Z(nome="Pedro Silva"); ad.rodada(z9, AGORA, {}, d, tb); assert not enviados(z9)
print("OK — documento de cliente vira aviso no privado da advogada responsável (pedido de 04/11)")
