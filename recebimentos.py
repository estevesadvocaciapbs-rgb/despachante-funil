"""Planilha mensal de parcelas a receber — sem IA.

No 1º dia útil de cada mês (Belém), lê no EasyJur as receitas em aberto e manda ao grupo "Financeiro
Escritório" uma planilha .xlsx com duas abas — as parcelas que vencem no mês e as atrasadas de meses
anteriores (vencimento, dias em atraso, cliente, valor, parcela, especificação, advogado, forma de
pagamento, situação e nº da receita) — e um resumo com totais por semana e por advogado. Se a Za.Ia
recusar o arquivo, a mesma lista vai em texto no grupo.

Roda pelo workflow "Parcelas do mês" (.github/workflows/recebimentos.yml), em dias 1 a 7 de cada mês;
o código decide se já é o 1º dia útil e se a planilha do mês já foi enviada (procura o resumo no grupo),
então rodar de novo não duplica. Manual: python recebimentos.py 2026-11 [--previa] [--so-planilha] [--dry-run].

Gasto no EasyJur: 2 listagens (status A e V, até o fim do mês) + 3 listagens por advogado (a listagem
não traz o advogado; o filtro id_advogado traz) + 1 get_pessoa por cliente (~55 chamadas por mês)
+ até 7 consultas de feriado.
Privacidade: o repositório é público; o log só leva contagens. A planilha é montada em memória e vai
direto para a Za.Ia, sem ser gravada no repositório.
"""

import io
import os
import re
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

import despachante
import secretaria

BRT = timezone(timedelta(hours=-3))
GRUPO_FINANCEIRO = "claude-grupo-18"
# O enviar_midia da Za.Ia só aceita número (tira tudo que não é dígito): para o grupo é preciso o ID de
# WhatsApp dele (18 dígitos, começa com 1203), que a Za.Ia guarda no contato com o nome do grupo.
CONTATO_GRUPO = "Financeiro Escritório"
TITULO = "📊 *Parcelas a receber"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
FORMAS = {"PI": "Pix", "BO": "Boleto", "CC": "Cartão de crédito", "CD": "Cartão de débito",
          "DI": "Dinheiro", "CH": "Cheque", "DP": "Depósito", "DA": "Débito automático", "TD": "TED"}
ADVOGADOS = {344269: "Dra. Danielle", 378457: "Dra. Fernanda", 344268: "Dr. Lucas"}
SEM_ADVOGADO = "—"
LIMITE_PARTE = 3500
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _log(msg):
    print(f"[{datetime.now(BRT):%d/%m %H:%M:%S}] recebimentos: {str(msg)[:300]}", flush=True)


def rotulo_mes(ano, mes):
    return f"{MESES[mes - 1]}/{ano}"


def fim_do_mes(ano, mes):
    return (date(ano, mes, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def primeiro_dia_util(ej, ano, mes):
    d = date(ano, mes, 1)
    while d.weekday() >= 5 or secretaria.e_feriado(ej, d):
        d += timedelta(days=1)
    return d


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- dados do EasyJur
def receitas_em_aberto(ej, ate, status=("A", "V"), **filtro):
    """Receitas não pagas nem canceladas com vencimento até `ate` (o EasyJur devolve as vencidas também
    com status "A"; pedir "V" junto é só garantia). Pagas e canceladas ficam de fora."""
    vistas = {}
    for st in status:
        for pagina in range(1, 21):
            r = ej.chamar("list_receitas", status=st, data_vencimento_fim=ate.isoformat(),
                          ordenar_por="data_vencimento", page_size=100, page=pagina, **filtro) or {}
            for x in r.get("data") or []:
                vistas.setdefault(x["id"], x)
            if pagina >= int((r.get("meta") or {}).get("total_pages") or 1):
                break
    return vistas


def advogado_por_receita(ej, ate):
    mapa = {}
    for aid, nome in ADVOGADOS.items():
        for rid in receitas_em_aberto(ej, ate, status=("A",), id_advogado=aid):
            mapa[rid] = nome
    return mapa


def nome_pessoa(ej, pid, cache):
    if not pid:
        return "(sem cliente vinculado)"
    if pid not in cache:
        p = (ej.chamar("get_pessoa", pessoa_id=int(pid)) or {}).get("data") or {}
        cache[pid] = re.sub(r"\s+", " ", (p.get("nome") or "").strip()).title() or f"(pessoa {pid})"
    return cache[pid]


def especificacao(r):
    desc = re.sub(r"^Honorarios\b", "Honorários", (r.get("descricao") or "").strip().capitalize())
    plano = ((r.get("tipo_receita") or {}).get("descricao") or "").strip()
    plano = re.sub(r"^[\d.]+\s*-?\s*", "", plano)  # "1.1.01 - Êxito" -> "Êxito"
    return " — ".join(p for p in (desc, plano) if p) or "—"


def linhas(ej, receitas, advogados, hoje, cache=None):
    cache, saida = ({} if cache is None else cache), []
    for r in receitas:
        parcela, parcelas = r.get("parcela"), r.get("parcelas")
        venc = date.fromisoformat((r.get("datas") or {}).get("vencimento"))
        saida.append({
            "venc": venc,
            "atraso": max((hoje - venc).days, 0),
            "cliente": nome_pessoa(ej, r.get("id_cliente") or r.get("id_pagador"), cache),
            "valor": float((r.get("valores") or {}).get("valor") or 0),
            "parcela": f"{parcela}/{parcelas}" if parcela and parcelas else "única",
            "espec": especificacao(r),
            "advogado": advogados.get(r["id"], SEM_ADVOGADO),
            "forma": FORMAS.get(r.get("forma_pagamento") or "", "—"),
            "situacao": "Vencida" if venc < hoje else "Em aberto",
            "id": r["id"],
        })
    saida.sort(key=lambda x: (x["venc"], x["cliente"]))
    return saida


def dados(ej, ano, mes, hoje):
    """(parcelas do mês, atrasadas de meses anteriores), com o advogado de cada receita."""
    fim = fim_do_mes(ano, mes)
    todas = receitas_em_aberto(ej, fim)
    advogados = advogado_por_receita(ej, fim)
    cache, inicio = {}, date(ano, mes, 1)
    do_mes = [r for r in todas.values() if r["datas"]["vencimento"] >= inicio.isoformat()]
    atrasadas = [r for r in todas.values() if r["datas"]["vencimento"] < inicio.isoformat()]
    return linhas(ej, do_mes, advogados, hoje, cache), linhas(ej, atrasadas, advogados, hoje, cache)


# ---------------------------------------------------------------- planilha .xlsx (sem bibliotecas)
# (título, largura, tipo, campo)
ABA_MES = [("Vencimento", 13, "data", "venc"), ("Cliente", 38, "txt", "cliente"), ("Valor", 14, "valor", "valor"),
           ("Parcela", 9, "txt", "parcela"), ("Especificação", 44, "txt", "espec"),
           ("Advogado", 15, "txt", "advogado"), ("Forma de pagamento", 18, "txt", "forma"),
           ("Situação", 11, "txt", "situacao"), ("Nº receita EasyJur", 18, "num", "id")]
ABA_ATRASO = [("Vencimento", 13, "data", "venc"), ("Dias em atraso", 14, "num", "atraso"),
              ("Cliente", 38, "txt", "cliente"), ("Valor", 14, "valor", "valor"), ("Parcela", 9, "txt", "parcela"),
              ("Especificação", 44, "txt", "espec"), ("Advogado", 15, "txt", "advogado"),
              ("Forma de pagamento", 18, "txt", "forma"), ("Nº receita EasyJur", 18, "num", "id")]
ESTILOS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="2"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/>'
    '<numFmt numFmtId="165" formatCode="&quot;R$&quot; #,##0.00"/></numFmts>'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFD9E2F3"/><bgColor indexed="64"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="6">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="165" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
S_CAB, S_DATA, S_VALOR, S_TOTAL, S_NEGRITO = 1, 2, 3, 4, 5


def _limpo(t):
    return escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(t)))


def _txt(ref, t, s=0):
    return f'<c r="{ref}" t="inlineStr" s="{s}"><is><t xml:space="preserve">{_limpo(t)}</t></is></c>'


def _num(ref, v, s=0):
    return f'<c r="{ref}" s="{s}"><v>{v}</v></c>'


def _celula(ref, tipo, v):
    if tipo == "data":
        return _num(ref, (v - date(1899, 12, 30)).days, S_DATA)
    if tipo == "valor":
        return _num(ref, round(v, 2), S_VALOR)
    if tipo == "num":
        return _num(ref, v)
    return _txt(ref, v)


def folha(colunas, itens, vazio):
    """XML de uma aba; devolve (xml, última linha com dados para o filtro)."""
    letra = {campo: chr(65 + i) for i, (_, _, _, campo) in enumerate(colunas)}
    ult = chr(64 + len(colunas))
    rows = ['<row r="1">' + "".join(_txt(f"{chr(65 + i)}1", c[0], S_CAB) for i, c in enumerate(colunas)) + "</row>"]
    for k, x in enumerate(itens, 2):
        rows.append(f'<row r="{k}">' + "".join(_celula(f"{letra[campo]}{k}", tipo, x[campo])
                                              for _, _, tipo, campo in colunas) + "</row>")
    n = len(itens) + 1
    if itens:
        t, cv = n + 1, letra["valor"]
        rows.append(f'<row r="{t}">' + _txt(f"{letra['cliente']}{t}", f"TOTAL ({len(itens)} parcelas)", S_NEGRITO)
                    + f'<c r="{cv}{t}" s="{S_TOTAL}"><f>SUM({cv}2:{cv}{n})</f>'
                    f'<v>{round(sum(x["valor"] for x in itens), 2)}</v></c></row>')
    else:
        rows.append(f'<row r="2">{_txt("A2", vazio)}</row>')
    cols = "".join(f'<col min="{i}" max="{i}" width="{c[1]}" customWidth="1"/>' for i, c in enumerate(colunas, 1))
    filtro = f'<autoFilter ref="A1:{ult}{n}"/>' if itens else ""
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
           'state="frozen"/></sheetView></sheetViews>'
           f'<cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData>{filtro}</worksheet>')
    return xml, (f"$A$1:${ult}${n}" if itens else None)


def planilha(abas):
    """abas: [(nome, colunas, itens, texto_se_vazia)] -> bytes do .xlsx."""
    folhas = [folha(colunas, itens, vazio) for _, colunas, itens, vazio in abas]
    nomes = [_limpo(nome[:31]) for nome, _, _, _ in abas]
    filtros = "".join(f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
                      f"'{nomes[i]}'!{ref}</definedName>" for i, (_, ref) in enumerate(folhas) if ref)
    livro = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
             'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
             + "".join(f'<sheet name="{nomes[i]}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i in range(len(abas)))
             + "</sheets>" + (f"<definedNames>{filtros}</definedNames>" if filtros else "") + "</workbook>")
    tipos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
             + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                       for i in range(len(abas)))
             + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    rels_livro = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                            for i in range(len(abas)))
                  + f'<Relationship Id="rId{len(abas) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                  '</Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipos)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", livro)
        z.writestr("xl/_rels/workbook.xml.rels", rels_livro)
        z.writestr("xl/styles.xml", ESTILOS)
        for i, (xml, _) in enumerate(folhas):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", xml)
    return buf.getvalue()


def planilha_do_mes(itens, atrasadas, ano, mes):
    return planilha([(f"{MESES[mes - 1].capitalize()} {ano}", ABA_MES, itens, "Nenhuma parcela em aberto neste mês."),
                     ("Atrasadas", ABA_ATRASO, atrasadas, "Nenhuma parcela atrasada de meses anteriores.")])


# ---------------------------------------------------------------- mensagens
def cabecalho(ano, mes, previa=False):
    return f"{TITULO} — {rotulo_mes(ano, mes)}*" + (" (prévia)" if previa else "")


def por_advogado(itens):
    soma = {}
    for x in itens:
        soma.setdefault(x["advogado"], []).append(x["valor"])
    ordem = list(ADVOGADOS.values()) + [SEM_ADVOGADO]
    return "\n".join(f"• {'Sem advogado' if a == SEM_ADVOGADO else a}: {brl(sum(v))} ({len(v)})"
                     for a, v in sorted(soma.items(), key=lambda kv: ordem.index(kv[0])))


def resumo(itens, atrasadas, ano, mes, previa=False, com_planilha=True):
    semanas = {}
    for x in itens:
        semanas.setdefault(x["venc"] - timedelta(days=x["venc"].weekday()), []).append(x["valor"])
    ultimo = fim_do_mes(ano, mes)

    def periodo(s):
        ini, fim = max(s, date(ano, mes, 1)), min(s + timedelta(days=6), ultimo)
        return f"{ini:%d/%m}" if ini == fim else f"{ini:%d/%m} a {fim:%d/%m}"

    topo = f"{cabecalho(ano, mes, previa)}\n{len(itens)} parcela(s) em aberto · total *{brl(sum(x['valor'] for x in itens))}*"
    blocos = []
    if semanas:
        blocos.append("Por semana:\n" + "\n".join(
            f"• {periodo(s)}: {brl(sum(v))} ({len(v)})" for s, v in sorted(semanas.items())))
        blocos.append("Por advogado:\n" + por_advogado(itens))
    if atrasadas:
        aba = ' (aba "Atrasadas" da planilha)' if com_planilha else ""
        blocos.append(f"⚠️ *Atrasadas de meses anteriores:* {len(atrasadas)} parcela(s) · "
                      f"*{brl(sum(x['valor'] for x in atrasadas))}*{aba}\n" + por_advogado(atrasadas))
    if com_planilha:
        blocos.append("_Planilha completa acima: aba do mês e aba de atrasadas (vencimento, cliente, valor, parcela, "
                      "especificação e advogado). Pagamento recebido: é só avisar aqui que eu dou a baixa "
                      "(ex.: dar baixa na parcela 3/12 do João, pagou 300 hoje por Pix)._")
    return "\n\n".join([topo] + blocos)


def lista_texto(itens, atrasadas):
    """Lista completa em texto (quando a Za.Ia não aceita o arquivo), em partes sem quebrar item."""
    linhas_txt = [f"{x['venc']:%d/%m} · *{x['cliente']}* · {brl(x['valor'])} · parcela {x['parcela']} · "
                  f"{x['espec']} · {x['advogado']} · {x['forma']}" for x in itens]
    if atrasadas:
        linhas_txt += ["", "⚠️ *Atrasadas de meses anteriores*"] + [
            f"{x['venc']:%d/%m/%Y} ({x['atraso']} dias) · *{x['cliente']}* · {brl(x['valor'])} · "
            f"parcela {x['parcela']} · {x['espec']} · {x['advogado']}" for x in atrasadas]
    partes, atual = [], []
    for l in linhas_txt:
        if atual and len("\n".join(atual + [l])) > LIMITE_PARTE:
            partes.append("\n".join(atual).strip("\n"))
            atual = []
        atual.append(l)
    if atual:
        partes.append("\n".join(atual).strip("\n"))
    return [p for p in partes if p]


def ja_enviado(zaia, ano, mes):
    msgs = (zaia.chamar("ler_grupo", grupoId=GRUPO_FINANCEIRO, limit=100) or {}).get("mensagens", [])
    alvo = cabecalho(ano, mes)
    return any(m.get("sender") != "CONTACT" and secretaria.sem_assinatura(m.get("content")).startswith(alvo)
               and not secretaria.sem_assinatura(m.get("content")).startswith(alvo + " (prévia)") for m in msgs)


def id_whatsapp_do_grupo(zaia):
    for c in (zaia.chamar("buscar_contatos", query=CONTATO_GRUPO) or {}).get("contatos", []):
        dig = re.sub(r"\D", "", c.get("phone") or "")
        if secretaria.norm(c.get("name")) == secretaria.norm(CONTATO_GRUPO) and len(dig) >= 18 and dig.startswith("1203"):
            return dig
    raise RuntimeError("contato do grupo não encontrado na Za.Ia")


def enviar_planilha(zaia, conteudo, nome, legenda):
    destino = id_whatsapp_do_grupo(zaia)
    prep = zaia.chamar("preparar_upload_midia", nomeArquivo=nome, mimetype=XLSX, tamanhoBytes=len(conteudo)) or {}
    # Sem User-Agent próprio, o Cloudflare da Za.Ia recusa o PUT do Python (HTTP 403, "error code: 1010").
    req = urllib.request.Request(prep["uploadUrl"], data=conteudo, method="PUT", headers={
        "Content-Type": XLSX, "User-Agent": "despachante-funil/2.0 (+https://github.com/estevesadvocaciapbs-rgb/despachante-funil)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()
    zaia.chamar("enviar_midia", assinatura="ia", numero=destino, uploadKey=prep["uploadKey"],
                nomeArquivo=nome, mimetype=XLSX, legenda=legenda)


def enviar(zaia, ej, ano, mes, previa=False, dry_run=False, so_planilha=False, hoje=None):
    hoje = hoje or datetime.now(BRT).date()
    itens, atrasadas = dados(ej, ano, mes, hoje)
    nome = f"parcelas-a-receber-{ano}-{mes:02d}.xlsx"
    conteudo = planilha_do_mes(itens, atrasadas, ano, mes)
    _log(f"{rotulo_mes(ano, mes)}: {len(itens)} parcela(s) no mês, {len(atrasadas)} atrasada(s); "
         f"planilha com {len(conteudo)} bytes")
    if dry_run:
        return itens, atrasadas, conteudo
    com_planilha = False
    if itens or atrasadas:
        try:
            enviar_planilha(zaia, conteudo, nome, cabecalho(ano, mes, previa).replace("*", ""))
            com_planilha = True
        except Exception as e:  # a lista em texto garante a entrega
            motivo = despachante.RE_TELEFONE_LOG.sub("[tel]", f"{type(e).__name__}: {e}")[:160]
            _log(f"planilha não enviada ao grupo ({motivo}); vai a lista em texto")
    if so_planilha:  # reenvio só do arquivo: o resumo e a lista já estão no grupo, nada mais sai
        return itens, atrasadas, conteudo
    zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=GRUPO_FINANCEIRO,
                texto=resumo(itens, atrasadas, ano, mes, previa, com_planilha))
    if not com_planilha:
        for parte in lista_texto(itens, atrasadas):
            zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=GRUPO_FINANCEIRO, texto=parte)
    return itens, atrasadas, conteudo


def rodada(zaia, ej, agora=None):
    """Envio automático: a partir do 1º dia útil do mês, uma vez (confere o resumo no grupo)."""
    local = (agora or datetime.now(timezone.utc)).astimezone(BRT)
    hoje = local.date()
    if hoje < primeiro_dia_util(ej, hoje.year, hoje.month):
        _log("ainda não é o 1º dia útil do mês")
        return False
    if ja_enviado(zaia, hoje.year, hoje.month):
        _log("planilha do mês já enviada")
        return False
    enviar(zaia, ej, hoje.year, hoje.month, hoje=hoje)
    return True


def main(argv):
    dry = "--dry-run" in argv
    zaia = despachante.MCP(despachante.ZAIA_URL, os.environ.get("ZAIA_TOKEN"), "Za.Ia")
    ej = despachante.MCP(despachante.EASYJUR_URL, os.environ.get("EASYJUR_TOKEN"), "EasyJur")
    m = next((re.fullmatch(r"(\d{4})-(\d{2})", a) for a in argv if re.fullmatch(r"\d{4}-\d{2}", a)), None)
    if m:  # envio manual de um mês escolhido (com --previa, não conta como o envio oficial)
        enviar(zaia, ej, int(m.group(1)), int(m.group(2)), previa="--previa" in argv, dry_run=dry,
               so_planilha="--so-planilha" in argv)
    elif not dry:
        rodada(zaia, ej)
    _log(f"chamadas ao EasyJur: {despachante.ESTADO_EJ['chamadas']}")


if __name__ == "__main__":
    main(sys.argv[1:])
