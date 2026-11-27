"""Teste do Em alta da sexta no porteiro (sem rede): python teste_em_alta.py"""
import porteiro as p

casos = {
    "EA SIM": "SIM", "ea sim agenda": "AGENDA", "EA sim, pode programar para sexta": "AGENDA",
    "*Dr. Lucas*:\nEA ok": "SIM", "EA reserva": "RESERVA", "EA não": "NAO", "EA nao, essa semana não": "NAO",
    "EA vou gravar": "GRAVO", "EA ajuste: troca o título": "AJUSTE", "EA foca em MEI": "PEDIDO",
    "Ea: autorizo": "SIM", "Bom dia": None, "Era isso": None, "EAD": None, "me manda o EA": None,
}
erros = 0
for texto, esperado in casos.items():
    obtido = p.comando_em_alta(texto)
    if obtido != esperado:
        erros += 1
        print(f"ERRO {texto!r}: {obtido} (esperado {esperado})")

gravados, enviados = [], []
p.gravar_no_ramo = lambda arq, conteudo, msg: gravados.append((arq, conteudo)) or True


class Zaia:
    def chamar(self, ferramenta, **args):
        enviados.append((ferramenta, args))


msgs = [{"sender": "USER", "content": "Responda EA SIM", "createdAt": "2026-11-27T20:00:00Z", "id": 1},
        {"sender": "CONTACT", "content": "EA sim agenda", "createdAt": "2026-11-27T20:05:00Z", "id": 2}]
from datetime import datetime, timezone
p._estado["ea_ultima"] = datetime(2000, 1, 1, tzinfo=timezone.utc)
p.olhar_em_alta(Zaia(), msgs, None)
p.olhar_em_alta(Zaia(), msgs, None)  # a mesma resposta lida de novo (outra volta ou plantão) não repete
assert len(gravados) == 1 and '"AGENDA"' in gravados[0][1] and "em_alta.json" == gravados[0][0], gravados
assert len(enviados) == 1 and enviados[0][1]["numero"] == p.LUCAS_TEL, enviados
assert not p.pedido_no_privado(msgs[1], "lucas"), "EA não pode acordar o Secretário"
print("ok" if not erros else f"{erros} erro(s)")
