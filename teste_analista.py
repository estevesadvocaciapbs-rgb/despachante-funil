"""Testes do analista de viabilidade (24/11), sem chamar a API (cliente falso). Dados fictícios.
Rodar: python teste_analista.py"""
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("ZAIA_TOKEN", "x")
os.environ.setdefault("EASYJUR_TOKEN", "x")
import analista as a  # noqa: E402
import despachante as d  # noqa: E402

AGORA = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)
TEL = "5594900000001"
PARECER = {"decisao": "ACAO_JUDICIAL", "nota": 8, "prova": 3, "solidez": 3, "valor": 1, "risco": 1,
           "teses": ["FGTS sem depósito há 8 meses", "salário atrasado"], "ponto_fragil": "testemunha não identificada",
           "perguntas_faltantes": ["Tem o extrato do FGTS?"], "recomendacao": "Agendar com prioridade.",
           "mensagem_ao_cliente": ""}


class Cliente:
    def __init__(self, parecer=PARECER, recusa=False):
        self.pedidos, self.parecer, self.recusa = [], parecer, recusa
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **k):
        self.pedidos.append(k)
        return SimpleNamespace(stop_reason="refusal" if self.recusa else "end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.parecer))])


class Zaia:
    def __init__(self, grupo=()):
        self.env, self.grupo = [], list(grupo)

    def chamar(self, f, **k):
        self.env.append((f, k))
        return {"mensagens": self.grupo} if f == "ler_grupo" else {}


MSGS = [{"sender": "CONTACT", "content": "Trabalho há 3 anos e não depositam meu FGTS",
         "createdAt": "2026-11-25T14:40:00.000Z"},
        {"sender": "AGENT", "content": "*Annie*: Entendi. Seu salário atrasa?", "createdAt": "2026-11-25T14:41:00.000Z"}]


class Conversas:
    def de(self, tel):
        return {"id": "c1", "contact": {"id": "k1", "name": "Fulano Teste"}}, MSGS


def lead(quando=AGORA - timedelta(minutes=10), texto="Área: Trabalhista. Rescisão indireta, FGTS não depositado."):
    return {"nome": "Fulano Teste", "tel": TEL, "texto": texto, "quando": quando, "origem": "grupo"}


def rodar(leads, cliente, grupo=(), env=True):
    a._estado.update(feitos=set(), dia=None, no_dia=0)
    if env:
        os.environ["ANTHROPIC_API_KEY"], os.environ["CRITERIOS_TRIAGEM"] = "teste", "CRITÉRIOS FICTÍCIOS"
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    z = Zaia(grupo)
    a.rodada(z, Conversas(), leads, {"mensagens": list(grupo)}, AGORA, {}, d, cliente)
    return z, [k["texto"] for f, k in z.env if f == "enviar_mensagem_grupo"]


assert d.classificar(lead()["texto"])[0] == "trabalhista", d.classificar(lead()["texto"])
# transcrição sem a assinatura da Annie e com quem falou
t = a.transcricao(MSGS, d)
assert "Cliente: Trabalho há 3 anos" in t and "Annie: Entendi." in t and "*Annie*" not in t
# lead trabalhista novo: um parecer no grupo, com a conversa e os critérios na chamada
c = Cliente()
z, enviados = rodar([lead()], c)
assert len(enviados) == 1 and "✅ Cabe ação judicial · nota 8/10" in enviados[0] and f"({TEL})" in enviados[0]
assert "modo teste" in enviados[0]
pedido = c.pedidos[0]
assert pedido["model"] == "claude-haiku-5-5" and "fallbacks" not in pedido and "CRITÉRIOS FICTÍCIOS" in pedido["system"][0]["text"]
assert "não depositam meu FGTS" in pedido["messages"][0]["content"]
assert pedido["output_config"]["format"]["type"] == "json_schema"
# não repete no mesmo plantão nem depois do reinício (parecer já no grupo)
z2, env2 = rodar([lead()], Cliente(), grupo=[{"content": enviados[0]}])
assert env2 == []
# sem a chave da API: não roda
assert rodar([lead()], Cliente(), env=False)[1] == []
# briefing antigo, recente demais ou de outra área: não analisa
assert rodar([lead(quando=AGORA - timedelta(hours=13))], Cliente())[1] == []
assert rodar([lead(quando=AGORA - timedelta(minutes=1))], Cliente())[1] == []
assert rodar([lead(texto="Área: Família. Pensão alimentícia do filho.")], Cliente())[1] == []
# recusa do modelo: nada vai ao grupo
assert rodar([lead()], Cliente(recusa=True))[1] == []
# mensagem sugerida só aparece em SEM_ACAO / NAO_INTERESSA
p = dict(PARECER, decisao="NAO_INTERESSA", nota=2, mensagem_ao_cliente="Obrigada por contar seu caso...")
txt = a.texto_parecer(p, "Fulano", TEL)
assert "⛔" in txt and "NÃO enviada" in txt
print("ok — analista de viabilidade (modo teste)")
