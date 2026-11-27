"""Painel de Gestão, parte do EasyJur (pedido do Dr. Lucas em 27/11/2026). Sem IA.

Duas vezes por dia (6h40 e 19h55 de Belém) manda para a planilha "Painel de Gestão – produtividade e custos":
- os prazos (agenda tipo PRAZO) de 7 dias atrás a 7 dias à frente: data, lançamento, status, advogado, cliente e
  descrição;
- os clientes com processo ativo (id da pessoa, nome e nº de processos).

Quem cruza os prazos com as pastas do Drive (documento novo para o prazo?) é o painel.gs, no Google, logo depois
(7h e 20h15). O EasyJur recusa o IP do VPS, por isso esta parte roda no GitHub. Destino: a mesma "Ponte Planilha"
das conversas do dia (segredos GOOGLE_PLANILHA_URL e GOOGLE_PLANILHA_CHAVE), ação "painel_easyjur".

Repositório PÚBLICO: o log mostra só contagens; nomes e descrições vão direto para a planilha (privada).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import despachante
from conversas_dia import BRT, ponte_padrao

JANELA_DIAS = 7


def _log(msg):
    despachante.log(f"[painel-easyjur] {msg}")


def _todas(ej, ferramenta, **filtros):
    itens = []
    for pagina in range(1, 31):
        r = ej.chamar(ferramenta, page=pagina, page_size=100, **filtros) or {}
        itens += r.get("data") or []
        if pagina >= int((r.get("meta") or {}).get("total_pages") or 1):
            break
    return itens


def _texto(s):
    """Desfaz acento quebrado do EasyJur ('ManifestaÃ§Ã£o' -> 'Manifestação') e junta os espaços."""
    s = " ".join(str(s or "").split())
    if "Ã" in s or "Â" in s:
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


def prazos(ej, hoje):
    lista = []
    for p in _todas(ej, "list_agenda", tipo="PRAZO", data_interna_inicio=(hoje - timedelta(days=JANELA_DIAS)).isoformat(),
                    data_interna_fim=(hoje + timedelta(days=JANELA_DIAS)).isoformat()):
        lista.append({"id": p.get("id"), "data": p.get("data") or "", "data_cadastro": p.get("data_cadastro") or "",
                      "status": p.get("status") or "", "advogado": p.get("advogado") or "",
                      "id_cliente": p.get("cliente") or "", "nome_cliente": _texto(p.get("nome_cliente")),
                      "processo": p.get("processo") or "",
                      "descricao": _texto(p.get("descricao"))[:300]})
    return lista


def clientes_ativos(ej):
    por_id = {}
    for p in _todas(ej, "list_processos", status="1"):
        pid = p.get("id_cliente")
        if not pid:
            continue
        c = por_id.setdefault(str(pid), {"id_pessoa": str(pid), "nome": _texto(p.get("nome_cliente")),
                                         "processos": 0})
        c["processos"] += 1
    return list(por_id.values())


def rodada(ej, ponte=ponte_padrao, agora=None, gravar=True):
    hoje = (agora or datetime.now(timezone.utc)).astimezone(BRT).date()
    pz, cl = prazos(ej, hoje), clientes_ativos(ej)
    abertos = sum(1 for p in pz if p["status"] not in ("C", "S"))
    _log(f"{len(pz)} prazo(s) entre {hoje - timedelta(days=JANELA_DIAS):%d/%m} e "
         f"{hoje + timedelta(days=JANELA_DIAS):%d/%m} ({abertos} em aberto); {len(cl)} cliente(s) com processo ativo")
    if gravar:
        r = ponte("painel_easyjur", prazos=pz, clientes=cl)
        _log(f"gravado no painel: {r.get('prazos')} prazo(s), {r.get('clientes')} cliente(s)")
    return pz, cl


def main(argv):
    simular = "--simular" in argv
    if not simular and not (os.environ.get("GOOGLE_PLANILHA_URL") and os.environ.get("GOOGLE_PLANILHA_CHAVE")):
        _log("planilha ainda não configurada; nada a fazer")
        return
    ej = despachante.MCP(despachante.EASYJUR_URL, os.environ.get("EASYJUR_TOKEN"), "EasyJur")
    try:
        rodada(ej, gravar=not simular)
    except Exception as e:
        _log(f"falhou: {type(e).__name__}: {e}")
        if not simular:
            zaia = despachante.MCP(despachante.ZAIA_URL, os.environ.get("ZAIA_TOKEN"), "Za.Ia")
            marca = f"{datetime.now(BRT):%d/%m %Hh}"
            if not despachante.ja_avisou_lucas(zaia, ("PAINEL EASYJUR", marca)):
                despachante.avisar_lucas(zaia, f"🛠️ *PAINEL EASYJUR {marca} — prazos não atualizados*\n"
                                         f"{type(e).__name__}: {str(e)[:200]}")
        raise
    finally:
        _log(f"chamadas ao EasyJur: {despachante.ESTADO_EJ['chamadas']}")


if __name__ == "__main__":
    main(sys.argv[1:])
