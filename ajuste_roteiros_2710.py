"""Ajuste dos roteiros da Annie aprovado pela usuária em 28/10/2026 (caso de 27/10: orientação de conduta na
triagem de assédio e familiar falando pela filha tratado como Suporte).

A) Nada de orientação de conduta: topo de cada passo dos roteiros de Rescisão Indireta.
B1) Familiar falando por outra pessoa é lead novo: Rescisão Indireta e Recepção.
B2) Lead novo nunca sai como contato de Suporte: Suporte.
C) Exclui o passo vazio "Novo passo" do roteiro de Assédio.

Cada bloco vai entre marcas próprias: rodar de novo não duplica, e "--desfazer" tira só o que foi posto aqui.
O log não leva texto de roteiro nem dado de cliente (o repositório é público).
"""

import os
import sys

import despachante as d

INICIO, FIM = "### AJUSTE 28/10 — INÍCIO ###", "### AJUSTE 28/10 — FIM ###"

A = """REGRA QUE PREVALECE SOBRE TODAS AS OUTRAS — NADA DE ORIENTAÇÃO DE CONDUTA:
1. É PROIBIDO orientar a pessoa (ou o familiar que fala por ela) sobre o que fazer ou deixar de fazer: pedir ou não demissão, assinar ou não carta ou documento, voltar ou não ao trabalho, faltar, procurar ou não o RH ou o INSS, aceitar ou recusar acordo.
2. Também é orientação, e também é proibido: elogiar ou aprovar uma decisão desse tipo ("fez muito bem em não assinar", "é bom mesmo segurar") e dizer que um ato "pode tirar direitos" ou "pode prejudicar".
3. Se a pessoa contar o que fez ou pretende fazer, só registre o fato no briefing, sem comentar.
4. Se ela perguntar o que fazer, ou se houver urgência (ex.: vai assinar a carta hoje), responda só: "Essa orientação quem dá é a Dra. Danielle Esteves no atendimento. Vou registrar que é urgente para a equipe te chamar o quanto antes." e siga a triagem. No briefing, comece o "Ponto a verificar" com "URGENTE:"."""

B1 = """FAMILIAR FALANDO POR OUTRA PESSOA: quando quem escreve é mãe, pai, filho, cônjuge ou outro familiar contando o problema de outra pessoa, é LEAD NOVO normal. Siga a triagem do assunto, perguntando sobre a pessoa que tem o problema ("ela", "ele"). Nunca transfira para o Suporte por isso. No briefing, LEAD é o nome de quem tem o problema, e a primeira linha do texto diz: "Quem entrou em contato: <nome>, <parentesco>, por este número.\""""

B2 = """LEAD NOVO NUNCA SAI COMO CONTATO DE SUPORTE: se a pessoa ainda não é cliente e trouxe um caso de qualquer área, inclusive Trabalhista, ou se é um familiar falando por ela, o aviso ao grupo e a tarefa são sempre ‼️NOVA OPORTUNIDADE‼️, com ÁREA e RESPONSÁVEL. Nunca use "Contato encaminhado pelo Suporte" para lead novo."""

PASSO_VAZIO = "claude-passo-140"


def sem_bloco(texto):
    if INICIO in texto and FIM in texto:
        antes, resto = texto.split(INICIO, 1)
        texto = antes + resto.split(FIM, 1)[1]
    return texto.strip()


def main(desfazer=False):
    zaia = d.MCP(d.ZAIA_URL, os.environ["ZAIA_TOKEN"], "Za.Ia")
    slugs = [r["slug"] for r in zaia.chamar("listar_roteiros")["roteiros"]]
    planos = {s: A + "\n\n" + B1 for s in slugs if s.startswith("resciso_indireta_")}
    planos["recepcao"] = B1
    planos["suporte"] = B2
    total = 0
    for slug, bloco in planos.items():
        if slug not in slugs:
            print(f"{slug}: roteiro não encontrado")
            continue
        feitos = 0
        for p in zaia.chamar("ler_roteiro", slug=slug)["passos"]:
            if p["id"] == PASSO_VAZIO:
                if not desfazer and not (p.get("instrucao") or "").strip():
                    zaia.chamar("excluir_passo", passoId=p["id"])
                    print(f"{slug}: passo vazio excluído")
                continue
            if not (p.get("instrucao") or "").strip() and not p.get("complementoUsuario"):
                continue
            atual = p.get("complementoUsuario") or ""
            limpo = sem_bloco(atual)
            novo = limpo if desfazer else f"{INICIO}\n{bloco}\n{FIM}\n\n{limpo}".strip()
            if novo != atual:
                zaia.chamar("editar_passo", passoId=p["id"], complemento=novo)
                feitos += 1
        print(f"{slug}: {feitos} passo(s) {'restaurado(s)' if desfazer else 'ajustado(s)'}")
        total += feitos
    print(f"total: {total}")


if __name__ == "__main__":
    main(desfazer="--desfazer" in sys.argv)
