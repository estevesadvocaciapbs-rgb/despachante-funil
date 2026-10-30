"""Competência de parcela em aberto = mês do vencimento, sem IA (pedido da usuária, 30/10).

O EasyJur grava em todas as parcelas a competência da primeira, e o resultado por mês fica distorcido. Uma vez por
dia, às 6h, acerta as receitas em aberto. Receita paga a API não deixa editar: fica como está. O log só leva contagem.
"""

from datetime import timedelta, timezone

BRT = timezone(timedelta(hours=-3))
HORA = 6
MAX_DIA = 200  # cota mensal da API: o que passar disso fica para o dia seguinte
_estado = {"dia": None}


def rodada(ej_fn, agora, log=print):
    local = agora.astimezone(BRT)
    if local.hour != HORA or _estado["dia"] == local.date():
        return
    _estado["dia"] = local.date()
    ej, feitas, erros = ej_fn(), 0, 0
    for status in ("A", "V"):
        pagina = 1
        while True:
            r = ej.chamar("list_receitas", status=status, page=pagina, page_size=100) or {}
            for x in r.get("data") or []:
                venc, comp = (x.get("datas") or {}).get("vencimento"), (x.get("datas") or {}).get("competencia")
                if not venc or (comp or "")[:7] == venc[:7]:
                    continue
                if feitas >= MAX_DIA:
                    log(f"competência: {feitas} parcela(s) acertada(s), o resto fica para amanhã")
                    return
                try:
                    ej.chamar("update_receita", receita_id=x["id"], data_competencia=venc)
                    feitas += 1
                except Exception as erro:
                    if type(erro).__name__ == "OrcamentoEasyJur":
                        raise
                    erros += 1
            if pagina >= ((r.get("meta") or {}).get("total_pages") or 1):
                break
            pagina += 1
    if feitas or erros:
        log(f"competência: {feitas} parcela(s) acertada(s), {erros} recusada(s)")
