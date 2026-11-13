"""Teste da etiqueta Tráfego Pago (dados inventados, sem rede)."""
from datetime import datetime, timezone

import despachante as d
import origem_trafego as o

AGORA = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def m(sender, texto, iso):
    return {"sender": sender, "content": texto, "createdAt": iso}


# mensagem pronta do anúncio (caso Belmiro/Reginaldo), "vi um anúncio" depois, e lead orgânico
assert o.veio_do_anuncio([m("CONTACT", "Olá! Quero sair do meu emprego e receber todos os meus benefícios", "1")], d)
assert o.veio_do_anuncio([m("CONTACT", "Oi, gostaria de saber mais sobre rescisão indireta", "1")], d)
assert o.veio_do_anuncio([m("CONTACT", "Bom dia", "1"), m("AGENT", "*Annie*: oi", "2"),
                          m("CONTACT", "Eu vi um anúncio no Facebook sobre quem trabalha...", "3")], d)
assert not o.veio_do_anuncio([m("CONTACT", "Boa tarde Dra Danielle", "1"),
                              m("CONTACT", "Gostaria de me orientar sobre licença maternidade", "2")], d)
assert not o.veio_do_anuncio([m("AGENT", "*Annie*: anúncio", "1")], d)  # só conta o que o cliente escreveu
print("OK — reconhece a mensagem pronta e a menção ao anúncio")


def at(n, tel, criada):
    return {"phone": tel, "contact": {"id": f"claude-contato-{n}"},
            "conversa": {"id": f"claude-conversa-{n}", "createdAt": criada}}


class FakeZ:
    def __init__(self):
        self.lidas, self.etiquetas = [], []
        self.conv = {
            "claude-conversa-1": [m("CONTACT", "Olá! Quero sair do meu emprego e receber todos os meus benefícios",
                                    "2026-11-13T12:29:13.000Z")],
            "claude-conversa-2": [m("CONTACT", "Boa tarde", "2026-11-13T10:00:00.000Z")],      # orgânico, antigo
            "claude-conversa-3": [m("CONTACT", "Oi", "2026-11-13T17:30:00.000Z")],             # recente: espera
        }

    def chamar(self, ferr, **x):
        if ferr == "listar_contatos":
            return {"contatos": [{"phone": "5594999990000"}]}
        if ferr == "listar_conversas":
            return {"atendimentos": [at(1, "5574998017910", "2026-11-13T12:29:44.000Z"),
                                     at(2, "5594988887777", "2026-11-13T10:00:00.000Z"),
                                     at(3, "5591977776666", "2026-11-13T17:29:00.000Z"),
                                     at(4, "5594999990000", "2026-11-13T09:00:00.000Z"),     # já etiquetado
                                     at(5, "5594992048054", "2026-11-13T09:00:00.000Z"),     # equipe
                                     at(6, "5594981112222", "2026-06-05T16:00:00.000Z")]}    # contato antigo
        if ferr == "ler_conversa":
            self.lidas.append(x["conversaId"])
            return {"messages": self.conv[x["conversaId"]]}
        if ferr == "adicionar_etiqueta_contato":
            self.etiquetas.append((x["contatoId"], x["etiquetaId"]))
            return {}
        raise AssertionError(ferr)


d.EQUIPE = set(d.EQUIPE) | {"5594992048054"}
z, cont = FakeZ(), {}
o.rodada(z, AGORA, cont, d)
assert z.etiquetas == [("claude-contato-1", "claude-etiqueta-14")] and cont["trafego_etiquetado"] == 1
assert z.lidas == ["claude-conversa-1", "claude-conversa-2", "claude-conversa-3"]
o.rodada(z, AGORA, cont, d)  # menos de 10 min: não lê de novo
assert len(z.lidas) == 3
o._estado["ultima"] = None
o.rodada(z, AGORA, cont, d)  # etiquetado e orgânico antigo ficam de fora; o recente é relido
assert z.lidas[3:] == ["claude-conversa-3"] and len(z.etiquetas) == 1
print("OK — etiqueta o lead do anúncio uma vez, ignora equipe/antigos e relê só a conversa recente")
