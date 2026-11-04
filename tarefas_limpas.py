"""Tarefas da Annie no Za.Ia: tira o raciocínio interno da descrição e junta os briefings repetidos, sem IA.

Pedidos da usuária (04/11, casos de 03/11 e 04/11):
- a plataforma cola no fim da tarefa os blocos "Resumo do atendimento:" e "Contexto:", que trazem o raciocínio
  da IA ("1) RELEITURA…", "6) AVANÇO…", "Decisão: …"). Fica o briefing, os dados coletados, o departamento, o
  contato, o que o contato disse depois e só a linha "Tom do cliente";
- cada vez que a Annie conclui de novo o passo final nasce outra tarefa de briefing do mesmo lead. Fica a mais
  antiga, com o briefing mais recente (a IA reescreve tudo a cada conclusão) e o que só as anteriores tinham;
  as repetidas são concluídas (não apagadas), com o título "DUPLICADA (ver claude-tarefa-N)".
O log não leva nome nem telefone (repositório público).
"""

import re
from datetime import datetime, timedelta

RACIOCINIO = ("Resumo do atendimento:", "Contexto:")
FICAM = ("Dados coletados:", "Departamento:", "Contato:", "O que o contato disse depois:")
RE_TOM = re.compile(r"Tom do cliente:\s*([A-ZÁÂÃÉÊÍÓÔÕÚÇ]+)")
CABECALHO = re.compile(r"^(‼️|⚠️|LEAD:|CONTATO:|ÁREA:|RESPONSÁVEL:|URGÊNCIA:)")
PARAGRAFO = re.compile(r"\n\s*\n")
MARCA_DUP = "DUPLICADA (ver "
JANELA_DUP = timedelta(days=3)
SEPARADOR = "Resumo do atendimento: (raciocínio interno da IA retirado)"
SO_ANTES = "Só nas tarefas anteriores:"
RODAPE = "(Briefing atualizado; "
LIMITE_ATUALIZACAO = 1500


def _ler(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _palavras(p):
    return re.findall(r"\w{4,}", p.lower())


def _parecido(bloco, paragrafos):
    """O parágrafo já está dito (mesmo reescrito pela IA): 60% das palavras dele aparecem num parágrafo de lá."""
    pal = set(_palavras(bloco))
    return not pal or any(len(pal & p) >= 0.6 * len(pal) for p in paragrafos)


def sem_raciocinio(descricao):
    """Descrição sem os blocos de raciocínio da IA; devolve a mesma se não houver o que tirar."""
    partes = PARAGRAFO.split(descricao or "")
    i = next((k for k, p in enumerate(partes) if p.lstrip().startswith(RACIOCINIO) and p.strip() != SEPARADOR), None)
    if i is None:
        return descricao
    tom = next((m.group(1) for p in partes[i:] for m in [RE_TOM.search(p)] if m), None)
    # o separador mantém o corte que o despachante usa para ler o briefing (resumo_do_caso, avaliar_trabalhista)
    ficam = partes[:i] + ([] if any(p.strip() == SEPARADOR for p in partes[:i]) else [SEPARADOR])
    if tom and not any(p.strip().startswith("Tom do cliente:") for p in partes[:i]):
        ficam.append(f"Tom do cliente: {tom}")
    ficam += [p for p in partes[i:] if p.lstrip().startswith(FICAM)]
    return "\n\n".join(p.strip() for p in ficam)


def e_briefing(t):
    titulo, desc = t.get("title") or "", t.get("description") or ""
    return ("NOVO LEAD" in titulo or titulo.startswith("Lead —") or "NOVA OPORTUNIDADE" in desc
            or "ATENDIMENTO INCOMPLETO" in desc) and MARCA_DUP not in titulo


def _dados(texto):
    """Campos de "Dados coletados:" (campo: valor) de uma descrição."""
    campos = {}
    for p in PARAGRAFO.split(texto):
        if p.lstrip().startswith("Dados coletados:"):
            for l in p.strip().splitlines()[1:]:
                k, _, v = l.partition(":")
                campos[k.strip()] = v.strip()
    return campos


def novidades(base, outra):
    """O que `outra` traz e `base` ainda não tem: parágrafos não ditos do briefing, o que o contato disse depois
    e, nos dados coletados, só o trecho acrescentado (sem o cabeçalho LEAD/ÁREA/RESPONSÁVEL)."""
    tem = [set(_palavras(p)) for p in PARAGRAFO.split(base)]
    pula = ("Departamento:", "Contato:", "Tom do cliente:", "Dados coletados:", SO_ANTES, RODAPE, SEPARADOR) + RACIOCINIO
    novos = []
    for p in PARAGRAFO.split(outra):
        bloco = "\n".join(l for l in p.strip().splitlines() if not CABECALHO.match(l.strip())).strip()
        if bloco and not bloco.startswith(pula) and not _parecido(bloco, tem):
            novos.append(bloco)
    velhos = _dados(base)
    for k, v in _dados(outra).items():
        antes = velhos.get(k, "")
        extra = v[len(antes):].strip() if antes and v.startswith(antes) else ("" if v == antes else v)
        if extra and not _parecido(extra, tem):
            novos.append(f"{k}: {extra}")
    return "\n\n".join(novos)


def juntar(anteriores, recente, ids):
    """Descrição da tarefa que fica: o briefing mais recente e, abaixo, o que só as tarefas anteriores tinham."""
    sobra = []
    for d in anteriores:
        extra = novidades("\n\n".join([recente] + sobra), d)
        if extra:
            sobra.append(extra)
    partes = [recente.strip()]
    if sobra:
        partes.append(f"{SO_ANTES}\n" + "\n\n".join(sobra)[:LIMITE_ATUALIZACAO])
    partes.append(f"{RODAPE}{', '.join(ids)} concluída(s) como repetida(s).)")
    return "\n\n".join(partes)


def rodada(zaia, tarefas, contagem, log, dry_run=False):
    abertas = [t for t in tarefas if not t.get("completedAt")]
    limpas = 0
    for t in abertas:
        nova = sem_raciocinio(t.get("description") or "")
        if nova != (t.get("description") or ""):
            if not dry_run:
                zaia.chamar("atualizar_tarefa", tarefaId=t["id"], campos={"descricao": nova})
            t["description"] = nova
            limpas += 1
    por_contato = {}
    for t in sorted((t for t in abertas if e_briefing(t) and t.get("contatoId")), key=lambda t: t["createdAt"]):
        por_contato.setdefault(t["contatoId"], []).append(t)
    juntadas = 0
    for grupo in por_contato.values():
        original = grupo[0]
        reps = [r for r in grupo[1:] if _ler(r["createdAt"]) - _ler(original["createdAt"]) <= JANELA_DUP]
        if not reps:
            continue
        nova = juntar([t.get("description") or "" for t in [original] + reps[:-1]],
                      reps[-1].get("description") or "", [r["id"] for r in reps])
        if not dry_run:
            zaia.chamar("atualizar_tarefa", tarefaId=original["id"], campos={"descricao": nova})
            for rep in reps:
                zaia.chamar("atualizar_tarefa", tarefaId=rep["id"],
                            campos={"titulo": f"{MARCA_DUP}{original['id']}) · {rep.get('title') or ''}"[:200]})
                zaia.chamar("completar_tarefa", tarefaId=rep["id"])
        original["description"] = nova
        juntadas += len(reps)
    if limpas or juntadas:
        contagem["tarefas_limpas"] = contagem.get("tarefas_limpas", 0) + limpas
        contagem["briefings_juntados"] = contagem.get("briefings_juntados", 0) + juntadas
        log(f"tarefas: {limpas} sem raciocínio da IA, {juntadas} briefing(s) repetido(s) juntado(s)")
