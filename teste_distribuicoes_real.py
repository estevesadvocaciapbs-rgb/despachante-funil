"""Simulação com os e-mails REAIS (25/11/2026): não cadastra nada, não manda mensagem.

Lê os avisos de distribuição pela Ponte Gmail, confere no EasyJur quais processos já existem e diz,
só em CONTAGENS (repositório público: nada de nome, número de processo ou texto de e-mail), quantos o robô
cadastraria. Roda à mão pelo workflow "Simulação: processo novo".
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

import agenda_google
import distribuicoes as di
from despachante import EASYJUR_URL, MCP
import os

BRT = timezone(timedelta(hours=-3))
hoje = datetime.now(BRT).date()
emails = agenda_google.distribuicoes(15)
if emails is None:
    raise SystemExit("Ponte Gmail não configurada (segredo GOOGLE_GMAIL_URL)")
ej = MCP(EASYJUR_URL, os.environ.get("EASYJUR_TOKEN"), "EasyJur")
c = Counter()
processos = {}
for e in emails:
    d = di.ler_email(e.get("texto") or "")
    if not d:
        c["e-mail que o robô não conseguiu ler"] += 1
        continue
    c["e-mail lido"] += 1
    processos[d["numero"]] = d
c["processos diferentes"] = len(processos)
for numero, d in processos.items():
    ramo = {"5": "TRT", "8": "TJ", "4": "TRF"}.get(d["justica"], "outro ramo")
    c["ramo " + ramo] += 1
    t = di.tribunal(d)
    if not t:
        c["tribunal não reconhecido"] += 1
    if di.recurso(d):
        c["recurso no 2º grau (só aviso)"] += 1
    if not d["autor"]:
        c["sem nome do cliente"] += 1
    if not d["reu"]:
        c["sem parte contrária"] += 1
    if t and di.comarca(ej, d["orgao"], t[3]):
        c["comarca achada"] += 1
    recente = (hoje - d["autuacao"]).days <= di.JANELA_DIAS
    ja = di.ja_cadastrado(ej, numero)
    c["já está no EasyJur"] += ja
    if recente and not ja:
        c["SERIA CADASTRADO AGORA (últimos 5 dias)"] += 1
    if not ja and not recente:
        c["fora do EasyJur, mas antigo (o robô ignora)"] += 1
print(f"Simulação com {len(emails)} e-mail(s) dos últimos 15 dias:")
for k, v in sorted(c.items()):
    print(f"  {k}: {v}")
