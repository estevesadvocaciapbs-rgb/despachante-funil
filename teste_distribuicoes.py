"""Testes do cadastro de processo novo a partir do e-mail de distribuição do PJe (25/11). Dados fictícios.
Rodar: python teste_distribuicoes.py"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import distribuicoes as di

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 16, 9, 0, tzinfo=BRT)
TRT = """________________________________
De: Processo Judicial Eletrônico - 1º Grau - Push <nao-responda@trt8.jus.br>
Assunto: [TRT08] [PUSH] Atualizações de Informações Processuais do Processo 0009999-11.2026.5.08.0114

Prezado(a) DIVA BRITO DE ANDRADE,

Informamos que o processo a seguir sofreu movimentação:

Número do Processo: 0009999-11.2026.5.08.0114

Classe Judicial: Ação Trabalhista - Rito Ordinário

Órgão Julgador: 1ª VARA DO TRABALHO DE PARAUAPEBAS

Data de Autuação: 14/11/2026 18:44:04

Autor:
FULANA DE TAL TESTE

Advogados do Autor: DIVA BRITO DE ANDRADE, OAB: 38229

Réu: EMPRESA FICTICIA LTDA e outros (1)

Advogados do Réu:

Eventos:

Data Evento
14/11/2026 18:44 Distribuído por sorteio
"""
TJPA = """TRIBUNAL DE JUSTIÇA DO ESTADO DO PARÁ
Prezado(a) DANIELLE MARTINS ESTEVES MOREIRA,
Informamos que o processo a seguir sofreu movimentação:
Número do Processo: 0888888-22.2026.8.14.0040
Polo Ativo: CICLANA DE SOUZA TESTE
Polo Passivo: BANCO FICTICIO S/A.
Classe Judicial: PROCEDIMENTO COMUM CÍVEL
Órgão: 1ª Vara Cível e Empresarial de Parauapebas
Data de Autuação: 12/11/2026
Tipo de Distribuição: sorteio
Assunto: Revisão de Juros
"""
MOVIMENTO = "Número do Processo: 0001111-11.2026.5.08.0114\nData de Autuação: 01/03/2026\nJuntada a petição"

d = di.ler_email(TRT)
assert d["numero"] == "0009999-11.2026.5.08.0114" and (d["justica"], d["tr"]) == ("5", "08")
assert d["autor"] == "FULANA DE TAL TESTE" and d["reu"] == "EMPRESA FICTICIA LTDA", (d["autor"], d["reu"])
assert d["orgao"] == "1ª VARA DO TRABALHO DE PARAUAPEBAS" and d["advogado"] == 372515
assert d["autuacao"].isoformat() == "2026-11-14" and d["classe"].startswith("Ação Trabalhista")
t = di.ler_email(TJPA)
assert t["autor"] == "CICLANA DE SOUZA TESTE" and t["reu"] == "BANCO FICTICIO S/A." and t["advogado"] == 344269
assert t["orgao"] == "1ª Vara Cível e Empresarial de Parauapebas" and t["assunto"] == "Revisão de Juros"
assert di.ler_email(MOVIMENTO) is None  # movimentação comum não é distribuição


class EasyJur:
    def __init__(self, processos=(), pessoas=()):
        self.processos, self.pessoas, self.chamadas = set(processos), list(pessoas), []

    def chamar(self, f, **k):
        self.chamadas.append((f, k))
        if f == "list_processos":
            n = k.get("numero") or k.get("n_desdobramento")
            return {"data": [{"id_processo": 1}] if n in self.processos else []}
        if f == "list_pessoas":
            alvo = di.normal(k["nome"]).split()
            return {"data": [p for p in self.pessoas if all(w in di.normal(p["nome"]).split() for w in alvo)]}
        if f == "create_pessoa":
            self.pessoas.append({"id": 900 + len(self.pessoas), "nome": k["nome"]})
            return {"id": self.pessoas[-1]["id"]}
        if f == "create_processo":
            self.processos.add(k["numero"])
            return {"id_processo": 555}
        raise AssertionError(f)


class Zaia:
    def __init__(self):
        self.env = []

    def chamar(self, f, **k):
        self.env.append(k.get("texto"))


D = SimpleNamespace(GRUPO="g", DRY_RUN=False)


def rodar(emails, ej, grupo=(), agora=AGORA):
    di._estado.update(ultima=None, vistos=set())
    z = Zaia()
    di.rodada(z, lambda: ej, lambda dias: [{"id": str(i), "texto": t} for i, t in enumerate(emails)], agora, {}, D,
              [{"content": c} for c in grupo])
    return z.env


# já cadastrado (o Claude cadastrou no protocolo): nada a fazer
ej = EasyJur(processos={"0009999-11.2026.5.08.0114"})
assert rodar([TRT], ej) == [] and not any(f.startswith("create") for f, _ in ej.chamadas)
# ninguém cadastrou: cria cliente e contrário novos, o processo, e avisa no grupo
ej = EasyJur()
env = rodar([TRT], ej)
cria = [k for f, k in ej.chamadas if f == "create_processo"][0]
assert cria["numero"] == "0009999-11.2026.5.08.0114" and cria["tribunal_orgao"] == 192 and cria["area"] == 6
assert cria["comarca"] == 2507 and cria["uf"] == "PA" and cria["id_advogado"] == 372515
assert cria["qualificacao"] == "Reclamante" and cria["distribuicao"] == "2026-11-14"
pj = [k for f, k in ej.chamadas if f == "create_pessoa"]
assert [p["fisica_juridica"] for p in pj] == ["F", "J"] and pj[0]["tipos"] == ["cliente"]
assert len(env) == 1 and "CADASTRADO PELO ROBÔ" in env[0] and "Cliente cadastrado agora" in env[0]
# cliente já existe com acento/grafia parecida (Sousa × Souza): usa o cadastro dele, não duplica
ej = EasyJur(pessoas=[{"id": 7, "nome": "Ciclana de Sousa Teste"}, {"id": 8, "nome": "Banco Fictício S/A."}])
env = rodar([TJPA], ej, agora=datetime(2026, 11, 13, 9, 0, tzinfo=BRT))
cria = [k for f, k in ej.chamadas if f == "create_processo"][0]
assert cria["id_cliente"] == 7 and cria["id_contrario"] == 8 and cria["tribunal_orgao"] == 191 and cria["area"] == 2
assert not any(f == "create_pessoa" for f, _ in ej.chamadas) and "Cliente cadastrado agora" not in env[0]
# já avisado no grupo (reinício do plantão): não repete
assert rodar([TRT], EasyJur(), grupo=[env[0], "📥 *PROCESSO NOVO CADASTRADO PELO ROBÔ* — 0009999-11.2026.5.08.0114"]) == []
# autuação antiga (e-mail de processo velho): ignora
assert rodar([TRT], EasyJur(), agora=AGORA + timedelta(days=10)) == []
# tribunal não configurado: não cadastra, só avisa
outro = TRT.replace("5.08.0114", "5.15.0001")
ej = EasyJur()
env = rodar([outro], ej)
assert len(env) == 1 and "SEM CADASTRO" in env[0] and not any(f.startswith("create") for f, _ in ej.chamadas)
# simulação: não cria nada
D.DRY_RUN = True
ej = EasyJur()
assert rodar([TRT], ej) == [] and not any(f.startswith("create") for f, _ in ej.chamadas)
D.DRY_RUN = False
# só roda de 30 em 30 minutos
di._estado.update(ultima=AGORA, vistos=set())
chamou = []
di.rodada(Zaia(), lambda: EasyJur(), lambda dias: chamou.append(1) or [], AGORA + timedelta(minutes=10), {}, D)
assert chamou == []
print("ok — processo novo distribuído")
