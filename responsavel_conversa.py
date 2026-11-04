"""Conversa de cliente da Dra. Fernanda fica no nome dela na Za.Ia, sem IA.

Pedido da usuária (04/11, caso Wellington): a Dra. Fernanda é "membro" na Za.Ia e só enxerga no celular as
conversas atribuídas a ela; os clientes dela não apareciam. A cada 30 minutos, a conversa aberta de quem
- tem o nome salvo terminando em "Fernanda" ("Wellington Cliente Fernanda", "Rubemar Criminal Fernanda"),
- tem a etiqueta PENDÊNCIA FERNANDA, ou
- tem tarefa aberta no kanban com ela de responsável
é atribuída a ela (atribuir_conversa). Cada conversa é atribuída uma vez por plantão. O log não leva nome.
"""

import time

ADVOGADAS = [  # (nome no contato, etiqueta, id do membro na Za.Ia, telefone dela, que fica de fora)
    ("fernanda", "PENDÊNCIA FERNANDA", "claude-usuario-3", "5594991742534"),
]
INTERVALO_S = 30 * 60
_feitas = set()
_ultima = [0.0]


def do_nome(contato, nome):
    """Contato salvo pela equipe com o nome da advogada no fim ("... Cliente Fernanda"), não a própria."""
    palavras = (contato.get("name") or "").strip().lower().split()
    return (len(palavras) >= 2 and palavras[-1] == nome and palavras[0] not in (nome, "dra.", "dra", "dr.")
            and "advogad" not in " ".join(palavras))


def contatos_da(zaia, nome, etiqueta, membro, tel_dela):
    ids = set()
    for c in zaia.chamar("buscar_contatos", query=nome.capitalize(), limit=50).get("contatos", []):
        if do_nome(c, nome) and c.get("phone") != tel_dela:
            ids.add(c["id"])
    for c in zaia.chamar("listar_contatos", etiqueta=etiqueta, limit=100).get("contatos", []):
        if c.get("phone") != tel_dela:
            ids.add(c["id"])
    for t in zaia.chamar("listar_tarefas", responsavelId=membro, limit=100).get("tarefas", []):
        if not t.get("completedAt") and t.get("contatoId"):
            ids.add(t["contatoId"])
    return ids


def rodada(zaia, contagem, log, dry_run=False, agora=None):
    agora = time.monotonic() if agora is None else agora
    if agora - _ultima[0] < INTERVALO_S:
        return
    _ultima[0] = agora
    for nome, etiqueta, membro, tel in ADVOGADAS:
        novas = 0
        for cid in sorted(contatos_da(zaia, nome, etiqueta, membro, tel)):
            for cv in zaia.chamar("listar_conversas_por_contato", contatoId=cid).get("conversas", []):
                if cv.get("status") != "OPEN" or (cv["id"], membro) in _feitas:
                    continue
                if not dry_run:
                    zaia.chamar("atribuir_conversa", conversaId=cv["id"], responsavelId=membro)
                _feitas.add((cv["id"], membro))
                novas += 1
        if novas:
            contagem["conversas_atribuidas"] = contagem.get("conversas_atribuidas", 0) + novas
            log(f"{novas} conversa(s) de cliente atribuída(s) à advogada ({membro})")
