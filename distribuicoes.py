"""Processo novo distribuído → cadastro no EasyJur (pedido da usuária em 25/11/2026).

Quando uma inicial é protocolada, o PJe manda à advogada que distribuiu um e-mail "Push" com o evento
"Distribuído por sorteio", o número, a vara, as partes e a data de autuação (TRT-8, TRT-1, TJPA...).
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
# CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO → (J, TR): (id do tribunal no EasyJur, área, qualificação do cliente)
TRIBUNAIS = {("5", "08"): (192, 6, "Reclamante"), ("5", "01"): (243, 6, "Reclamante"),
             ("8", "14"): (191, 2, "Autor"), ("8", "19"): (242, 2, "Autor")}
COMARCAS = {"parauapebas": 2507}
UF = {"08": "PA", "14": "PA", "01": "RJ", "19": "RJ"}
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
        m = re.search(rf"^[ \t]*{r}:[ \t]*\n?[ \t]*(\S.*?)[ \t]*$", texto, re.M)
        if m and m.group(1).strip():
            return m.group(1).strip()
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
    origem, area, qualificacao = TRIBUNAIS[(d["justica"], d["tr"])]
    cliente, c_novo = pessoa(ej, d["autor"], "cliente")
    contrario, x_novo = pessoa(ej, d["reu"], "parte_adversa") if d["reu"] else (None, False)
    comarca = next((v for k, v in COMARCAS.items() if k in normal(d["orgao"])), None)
    obs = (f"Cadastrado pelo robô em {datetime.now():%d/%m/%Y} a partir do e-mail de distribuição do tribunal "
           f"(autuação {d['autuacao']:%d/%m/%Y}). Conferir: valor da causa, pedidos, pasta do cliente e ativar o PUSH."
           + (f" Assunto: {d['assunto']}." if d["assunto"] else ""))
    r = ej.chamar("create_processo", numero=d["numero"], id_advogado=d["advogado"], id_cliente=cliente,
                  id_contrario=contrario, area=area, tribunal_orgao=origem, comarca=comarca, uf=UF.get(d["tr"]),
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
        if (d["justica"], d["tr"]) not in TRIBUNAIS or not d["autor"]:
            motivo = "tribunal ainda não configurado" if d["autor"] else "e-mail sem o nome do cliente"
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
