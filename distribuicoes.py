"""Processo novo distribuído → cadastro no EasyJur (pedido da usuária em 25/11/2026).

Quando uma inicial é protocolada, o PJe manda à advogada que distribuiu um e-mail "Push" com o evento
"Distribuído por sorteio", o número, a vara, as partes e a data de autuação (qualquer TRT, TJ ou TRF).
Esses e-mails são encaminhados ao Gmail do escritório; a ponte Google (Apps Script) os entrega aqui.

A cada 30 minutos:
- processo já cadastrado no EasyJur (o Claude cadastra quando protocola) → nada a fazer;
- processo que ninguém cadastrou → o robô cadastra (cliente, parte contrária, vara, data, advogada)
  e avisa no grupo para completar valor da causa, pedidos e o PUSH.
Na dúvida (tribunal desconhecido, e-mail incompleto), não cadastra: só avisa no grupo.
Privacidade: repositório público. O log leva só contagens, nunca nome nem número de processo.
"""

import re
import unicodedata
from datetime import datetime, timedelta

INTERVALO = timedelta(minutes=30)
JANELA_DIAS = 5          # autuação mais velha que isso não é "processo novo"
MARCA = "📥 *PROCESSO NOVO"
ADVOGADOS = {"danielle": 344269, "diva": 372515, "fernanda": 378457, "lucas": 344268}
DANIELLE = 344269
# CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO. Vale para QUALQUER TRT (J=5), TJ (J=8) e TRF (J=4) (pedido de 25/11:
# aparecem clientes de outros estados, ex. TRT-19). Ids = tribunais do EasyJur (campo origem).
TRT = {1: 243, 2: 301, 3: 172, 4: 266, 5: 123, 6: 210, 7: 130, 8: 192, 9: 229, 10: 135, 11: 114, 12: 276,
       13: 198, 14: 256, 15: 302, 16: 158, 17: 144, 18: 153, 19: 108, 20: 281, 21: 252, 22: 214, 23: 188, 24: 179}
UF_TRT = {1: "RJ", 2: "SP", 3: "MG", 4: "RS", 5: "BA", 6: "PE", 7: "CE", 8: "PA", 9: "PR", 10: "DF", 11: "AM",
          12: "SC", 13: "PB", 14: "RO", 15: "SP", 16: "MA", 17: "ES", 18: "GO", 19: "AL", 20: "SE", 21: "RN",
          22: "PI", 23: "MT", 24: "MS"}
# TJ: código TR do CNJ → (UF, id no EasyJur)
TJ = {1: ("AC", 104), 2: ("AL", 107), 3: ("AP", 116), 4: ("AM", 350), 5: ("BA", 122), 6: ("CE", 129),
      7: ("DF", 134), 8: ("ES", 143), 9: ("GO", 152), 10: ("MA", 157), 11: ("MT", 187), 12: ("MS", 178),
      13: ("MG", 170), 14: ("PA", 191), 15: ("PB", 197), 16: ("PR", 228), 17: ("PE", 209), 18: ("PI", 213),
      19: ("RJ", 242), 20: ("RN", 251), 21: ("RS", 265), 22: ("RO", 255), 23: ("RR", 257), 24: ("SC", 275),
      25: ("SE", 280), 26: ("SP", 299), 27: ("TO", 305)}
TRF = {1: 344, 2: 345, 3: 351, 4: 347, 5: 348, 6: 1059}
AREA = {"trabalhista": 6, "civel": 2, "previdenciario": 5, "tributario": 7}


def tribunal(d):
    """(id do tribunal, área, qualificação do cliente, UF) ou None se o ramo/tribunal não for TRT, TJ ou TRF."""
    j, tr = d["justica"], int(d["tr"])
    if j == "5" and tr in TRT:
        return TRT[tr], AREA["trabalhista"], "Reclamante", UF_TRT[tr]
    if j == "8" and tr in TJ:
        return TJ[tr][1], AREA["civel"], "Autor", TJ[tr][0]
    if j == "4" and tr in TRF:
        area = AREA["tributario"] if "tribut" in normal(d["assunto"] + " " + d["classe"]) else AREA["previdenciario"]
        return TRF[tr], area, "Autor", None
    return None


def recurso(d):
    """Agravo, apelação, recurso etc. (ou número de 2º grau, final .0000): no EasyJur é desdobramento, não processo novo."""
    return d["numero"].endswith(".0000") or bool(re.search(r"agravo|apela|recurso|embargos", normal(d["classe"])))


def comarca(ej, orgao, uf):
    """Id da comarca pela cidade no fim do nome da vara ("Vara do Trabalho de Parauapebas",
    "Vara Única de São Félix do Xingu"): busca pela última palavra e aceita o nome que fecha com o fim da vara."""
    texto = re.sub(r"\s*[-/]\s*[A-Z]{2}\s*$", "", orgao or "")
    palavras = normal(texto).split()
    candidatos = {" ".join(palavras[i + 1:]) for i, w in enumerate(palavras[:-1]) if w in ("de", "da", "do")}
    if not candidatos:
        return None
    args = {"nome": palavras[-1], "page_size": 50}
    if uf:
        args["uf"] = uf
    for c in _lista(ej.chamar("list_comarcas", **args)):
        if normal(c.get("nome")) in candidatos:
            return c.get("id")
    return None


RE_CNJ = re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.(\d)\.(\d{2})\.\d{4})\b")
EMPRESA = re.compile(r"\b(ltda|s\.?\s?a\.?|s/a|eireli|me|epp|mei|banco|cia|companhia|instituto|inss|"
                     r"municipio|estado|uniao|associacao|cooperativa|condominio|engenharia|servicos|comercio)\b")
_estado = {"ultima": None, "vistos": set()}


def _log(msg):
    print(f"distribuicoes: {msg}", flush=True)


def normal(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def _campo(texto, *rotulos):
    for r in rotulos:
        for m in re.finditer(rf"^[ \t]*{r}:[ \t]*\n?[ \t]*(\S.*?)[ \t]*$", texto, re.M):
            v = m.group(1).strip()
            # "Assunto:" do cabeçalho do e-mail encaminhado ("[TRT08] [PUSH] ...") não é campo do processo
            if v and not re.match(r"\[|(RES|ENC|FW|FWD|RE):|Movimenta[cç][aã]o processual", v, re.I):
                return v
    return ""


def ler_email(texto):
    """Extrai os dados do e-mail Push do PJe. None se não for um aviso de distribuição."""
    if not re.search(r"Distribu[ií]do por|Tipo de Distribui[cç][aã]o", texto):
        return None
    numero = _campo(texto, "Número do Processo", "Numero do Processo")
    m = RE_CNJ.search(numero)
    autuacao = re.search(r"Data de Autua[cç][aã]o:\s*(\d{2}/\d{2}/\d{4})", texto)
    if not m or not autuacao:
        return None
    autor = _campo(texto, "Autor", "Polo Ativo", "Reclamante", "Requerente")
    reu = _campo(texto, "Réu", "Reu", "Polo Passivo", "Reclamado", "Requerido")
    reu = re.sub(r"\s+e outros\s*\(\d+\)\s*$", "", reu, flags=re.I)
    advs = _campo(texto, "Advogados do Autor", "Advogados do Reclamante")
    prezado = re.search(r"Prezado\(a\)\s*([^,\n]+)", texto)
    return {"numero": m.group(1), "justica": m.group(2), "tr": m.group(3),
            "autuacao": datetime.strptime(autuacao.group(1), "%d/%m/%Y").date(),
            "classe": _campo(texto, "Classe Judicial", "Classe"),
            "orgao": _campo(texto, "Órgão Julgador", "Orgão Julgador", "Órgão", "Orgao"),
            "assunto": _campo(texto, "Assunto"),
            "autor": autor, "reu": reu,
            "advogado": _advogado(advs + " " + (prezado.group(1) if prezado else ""))}


def _advogado(texto):
    n = normal(texto)
    for nome, ident in ADVOGADOS.items():
        if nome in n.split():
            return ident
    return DANIELLE


def _lista(resp):
    return (resp or {}).get("data", []) if isinstance(resp, dict) else []


def ja_cadastrado(ej, numero):
    if _lista(ej.chamar("list_processos", numero=numero, page_size=1)):
        return True
    return bool(_lista(ej.chamar("list_processos", n_desdobramento=numero, page_size=1)))


def achar_pessoa(ej, nome):
    """Id da pessoa com esse nome: igual (sem acento/caixa) ou, se só houver uma, com mesmo primeiro e último nome."""
    alvo = normal(nome).split()
    if not alvo:
        return None
    vistos = {}
    for busca in {nome, f"{alvo[0]} {alvo[-1]}" if len(alvo) > 1 else nome}:
        for p in _lista(ej.chamar("list_pessoas", nome=busca, page_size=20)):
            vistos[p.get("id") or p.get("id_pessoa")] = normal(p.get("nome"))
    iguais = [i for i, n in vistos.items() if n == " ".join(alvo)]
    if iguais:
        return iguais[0]
    parecidos = [i for i, n in vistos.items() if n.split()[:1] == alvo[:1] and n.split()[-1:] == alvo[-1:]]
    return parecidos[0] if len(parecidos) == 1 else None


def pessoa(ej, nome, tipo):
    """Acha ou cadastra. Devolve (id, nova?)."""
    ident = achar_pessoa(ej, nome)
    if ident:
        return ident, False
    fj = "J" if EMPRESA.search(normal(nome)) else "F"
    r = ej.chamar("create_pessoa", nome=nome.strip(), fisica_juridica=fj, tipos=[tipo])
    r = r.get("data", r) if isinstance(r, dict) else {}
    return r.get("id") or r.get("id_pessoa"), True


def cadastrar(ej, d):
    """Cria o processo. Devolve (id_processo, cliente_novo?, contrario_novo?)."""
    origem, area, qualificacao, uf = tribunal(d)
    cliente, c_novo = pessoa(ej, d["autor"], "cliente")
    contrario, x_novo = pessoa(ej, d["reu"], "parte_adversa") if d["reu"] else (None, False)
    id_comarca = comarca(ej, d["orgao"], uf)
    obs = (f"Cadastrado pelo robô em {datetime.now():%d/%m/%Y} a partir do e-mail de distribuição do tribunal "
           f"(autuação {d['autuacao']:%d/%m/%Y}). Conferir: valor da causa, pedidos, pasta do cliente e ativar o PUSH."
           + (f" Assunto: {d['assunto']}." if d["assunto"] else ""))
    r = ej.chamar("create_processo", numero=d["numero"], id_advogado=d["advogado"], id_cliente=cliente,
                  id_contrario=contrario, area=area, tribunal_orgao=origem, comarca=id_comarca, uf=uf,
                  distribuicao=d["autuacao"].isoformat(), vara_turma=d["orgao"][:255] or None,
                  titulo_acao=d["classe"] or None, qualificacao=qualificacao, instancia="1",
                  status_processo=1, tipo_processo="judicial", observacoes=obs)
    r = r.get("data", r) if isinstance(r, dict) else {}
    return r.get("id_processo") or r.get("id"), c_novo, x_novo


def aviso(d, novo_cliente, novo_contrario):
    linhas = [f"{MARCA} CADASTRADO PELO ROBÔ* — {d['numero']}",
              f"{d['autor']} × {d['reu'] or '?'}",
              f"{d['orgao'] or 'vara ?'} · distribuído em {d['autuacao']:%d/%m/%Y}",
              "Veio do e-mail de distribuição do tribunal; não estava no EasyJur.",
              "*Falta completar:* valor da causa, pedidos, pasta do cliente e ativar o PUSH (24 h depois da distribuição)."]
    if novo_cliente:
        linhas.append("⚠️ Cliente cadastrado agora: confira se já existia com outro nome e junte os cadastros.")
    if novo_contrario:
        linhas.append("Parte contrária cadastrada agora (sem CNPJ).")
    return "\n".join(linhas)


def aviso_manual(d, motivo):
    return (f"{MARCA} SEM CADASTRO* — {d['numero']}\n{d['autor']} × {d['reu'] or '?'}\n"
            f"O robô não cadastrou ({motivo}). Cadastre à mão no EasyJur, por favor.")


def rodada(zaia, easyjur_fn, buscar_emails, agora, contagem, d_mod, grupo_msgs=()):
    """buscar_emails(dias) → [{'id','texto'}]; d_mod: o despachante (GRUPO, DRY_RUN)."""
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    emails = buscar_emails(JANELA_DIAS)
    if emails is None:
        return
    ja_avisados = " ".join(m.get("content") or "" for m in grupo_msgs if MARCA in (m.get("content") or ""))
    novos = {}
    for e in emails:
        d = ler_email(e.get("texto") or "")
        if d and d["numero"] not in _estado["vistos"] and (agora.date() - d["autuacao"]).days <= JANELA_DIAS:
            novos[d["numero"]] = d
    feitos = 0
    for numero, d in novos.items():
        _estado["vistos"].add(numero)
        if numero in ja_avisados:
            continue
        ej = easyjur_fn()
        if ja_cadastrado(ej, numero):
            continue
        if d_mod.DRY_RUN:
            _log("[simulação] cadastraria um processo novo")
            continue
        if not tribunal(d) or not d["autor"] or recurso(d):
            motivo = ("é recurso no 2º grau: cadastre como desdobramento do processo de origem" if recurso(d)
                      else "não é TRT, TJ nem TRF" if d["autor"] else "e-mail sem o nome do cliente")
            zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=d_mod.GRUPO, texto=aviso_manual(d, motivo))
            continue
        try:
            _, c_novo, x_novo = cadastrar(ej, d)
        except Exception as erro:
            _log(f"cadastro falhou: {type(erro).__name__}")
            zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=d_mod.GRUPO,
                        texto=aviso_manual(d, "o EasyJur recusou"))
            continue
        zaia.chamar("enviar_mensagem_grupo", assinatura="ia", grupoId=d_mod.GRUPO, texto=aviso(d, c_novo, x_novo))
        feitos += 1
    contagem["processos_cadastrados"] = contagem.get("processos_cadastrados", 0) + feitos
    _log(f"{len(emails)} e-mail(s), {len(novos)} distribuição(ões) nova(s), {feitos} cadastrada(s)")
