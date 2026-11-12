"""Arquivos do cliente para a pasta dele no Drive, sem IA (pedido da usuária, 12/11/2026).

A integração do Drive da Za.Ia salva toda mídia do WhatsApp em "Mídias - Whatsapp" › telefone, e a limpeza das
21h manda para a lixeira o que fica lá mais de 7 dias. Agora o aviso "📎 DOCUMENTO DE CLIENTE" ao advogado leva um
código D (D1, D2...) e diz o que vai acontecer com os arquivos:

- cliente com pasta em Processos › ÁREA › Nome: os arquivos vão para "Docs de Prova" dela 1 hora depois do aviso,
  a não ser que o advogado responda NÃO PASTA D3 (PASTA D3 guarda na hora);
- cliente sem pasta, mas com documentos pedidos depois da reunião (lista de documentos na conversa): a pasta é
  criada na área do caso e os arquivos vão para ela, também 1 hora depois (PASTA D3 FAMÍLIA troca a área);
- cliente sem pasta e sem pedido de documentos: nada é criado; o advogado cria a pasta e responde PASTA D3;
- mais de uma pasta com o nome: o advogado escolhe com PASTA D3 1 (ou 2...).

O estado fica nas próprias mensagens do privado do advogado (o aviso com o código e a resposta ✅/👍/⚠️/❓), então
reiniciar o plantão não repete nada. Quem move os arquivos é a ponte do Google (Apps Script da conta do escritório).
O log não leva nome nem telefone (repositório público).
"""

import re
from datetime import datetime, timedelta, timezone

INTERVALO = timedelta(minutes=5)
AUTO_APOS = timedelta(hours=1)
VALIDADE = timedelta(days=7)          # depois disso a limpeza das 21h já levou os arquivos para a lixeira
JANELA_PEDIDO = timedelta(days=45)    # pedido de documentos depois da reunião
AREAS = {"trabalhista": "TRABALHISTA", "previdenciario": "PREVIDENCIÁRIO", "civel": "CÍVEL", "familia": "FAMÍLIA",
         "criminal": "CRIMINAL"}
RE_AREA_TEXTO = [("PREVIDENCIÁRIO", r"previdenci|\binss\b|bpc|loas|aposentad|auxilio"),
                 ("CRIMINAL", r"criminal|\bpenal\b|inquerito|delegacia"),
                 ("FAMÍLIA", r"familia|divorci|pensao|guarda|violencia domestica|inventario"),
                 ("TRABALHISTA", r"trabalhist|rescis|demiti|demissao|\bclt\b|empregador|assedio"),
                 ("CÍVEL", r"civel|consumidor|tributari|indeniza|contrato")]
RE_PEDIDO_DOCS = re.compile(r"documento.{0,120}(envi|mand|encaminh|precis|lista|providenc)|"
                            r"(envi|mand|encaminh|precis|lista|providenc).{0,120}documento")
RE_RESPOSTA = re.compile(r"^\s*\*?(nao\s+)?pasta\s+d(\d{1,3})\b\s*(.*?)\s*\*?\s*$")
RE_CODIGO_AVISO = re.compile(r"📂 \*D(\d{1,3})\*")
RE_MARCA = re.compile(r"^(✅|👍|⚠️|❓) \*D(\d{1,3})\*")
RE_CABECALHO = re.compile(r"DOCUMENTO DE CLIENTE — (.+?) \((\d{10,13})\)\*")
RE_PRIMEIRO = re.compile(r"pelo WhatsApp em (\d{2})/(\d{2}) (\d{2}):(\d{2})")
RE_ULTIMO = re.compile(r"\(último às (\d{2})/(\d{2}) (\d{2}):(\d{2})\)")
RE_CRIAR = re.compile(r"vou criar a pasta Processos › (.+?) › (.+?) e guardar")
PALAVRAS_FORA = {"cliente", "dra", "dr", "fernanda", "lucas", "danielle", "dani", "thalyta", "lead", "criminal",
                 "trabalhista", "familia", "civel", "previdenciario", "consumidor"}
_estado = {"ultima": None}
_feito = set()   # (telefone do advogado, código, id da resposta) já tratados neste plantão


def nome_limpo(nome, d):
    """'Wellington Souza Cliente Fernanda' -> 'wellington souza'; 'Rubemar Criminal Fernanda' -> 'rubemar'."""
    palavras = re.sub(r"[^a-z ]", " ", d.sem_acento(nome or "").lower()).split()
    if "cliente" in palavras:
        palavras = palavras[:palavras.index("cliente")]
    while palavras and palavras[-1] in PALAVRAS_FORA:
        palavras.pop()
    return " ".join(w for w in palavras if len(w) > 1 and w not in ("dra", "dr"))


def nome_da_pasta(nome, area, adv, d):
    base = " ".join(w.capitalize() if w not in ("de", "da", "do", "das", "dos", "e") else w
                    for w in nome_limpo(nome, d).split())
    return base + (" - FERNANDA" if adv is d.FERNANDA and area == "TRABALHISTA" else "")


def area_do_caso(contato, tarefas, adv, d):
    textos = [d.sem_acento(f"{t.get('titulo') or t.get('title') or ''} {t.get('descricao') or t.get('description') or ''}")
              .lower() for t in tarefas if t.get("contatoId") == (contato or {}).get("id")]
    textos.append(d.sem_acento(" ".join(e.get("name") or "" for e in (contato or {}).get("labels") or [])).lower())
    for area, padrao in RE_AREA_TEXTO:
        if any(re.search(padrao, t) for t in textos):
            return area
    return "FAMÍLIA" if adv is d.FERNANDA else "CÍVEL" if adv is d.LUCAS else "TRABALHISTA"


def pediram_documentos(msgs, agora, d):
    """O escritório pediu documentos ao cliente (lista depois da reunião, M4/M5/M6) nos últimos 45 dias?"""
    return any(m.get("sender") != "CONTACT" and agora - d.ler_iso(m["createdAt"]) <= JANELA_PEDIDO
               and RE_PEDIDO_DOCS.search(d.sem_acento(m.get("content") or "").lower()) for m in msgs)


def proximo_codigo(msgs_adv):
    usados = [int(x) for m in msgs_adv for x in RE_CODIGO_AVISO.findall(m.get("content") or "")]
    return max(usados, default=0) + 1


def bloco_aviso(codigo, nome, contato, msgs_cliente, tarefas, adv, agora, d):
    """Linhas finais do aviso de documento: o que vai acontecer com os arquivos. None se a ponte não existe."""
    import agenda_google
    limpo = nome_limpo(nome, d)
    if len(limpo.split()) < 2:
        return (f"📂 *D{codigo}* — o contato está salvo só como \"{limpo.title() or nome}\" na Za.Ia e assim não acho a "
                f"pasta dele. Salve o nome completo e responda *PASTA D{codigo}* que eu guardo os arquivos.")
    cand = agenda_google.procurar_pasta(limpo)
    if cand is None:
        return None
    hora = (agora + AUTO_APOS).astimezone(d.BRT).strftime("%H:%M")
    if len(cand) == 1:
        return (f"📂 *D{codigo}* — vou guardar em {cand[0]['caminho']} › Docs de Prova às {hora}.\n"
                f"Para *não* guardar, responda *NÃO PASTA D{codigo}*. Para guardar já, *PASTA D{codigo}*.")
    if cand:
        opcoes = "\n".join(f"{i}) {c['caminho']}" for i, c in enumerate(cand[:6], 1))
        return (f"📂 *D{codigo}* — achei mais de uma pasta com esse nome:\n{opcoes}\n"
                f"Responda *PASTA D{codigo} 1* (ou o número certo) que eu guardo lá.")
    if pediram_documentos(msgs_cliente, agora, d):
        area = area_do_caso(contato, tarefas, adv, d)
        return (f"📂 *D{codigo}* — o cliente ainda não tem pasta. Como os documentos foram pedidos depois da reunião, "
                f"vou criar a pasta Processos › {area} › {nome_da_pasta(nome, area, adv, d)} e guardar às {hora}.\n"
                f"Área errada? Responda *PASTA D{codigo} FAMÍLIA* (ou a área certa). "
                f"Para *não* guardar, *NÃO PASTA D{codigo}*.")
    return (f"📂 *D{codigo}* — não achei a pasta deste cliente em Processos. Os arquivos ficam em \"Mídias - Whatsapp\" "
            f"e vão para a lixeira em 7 dias. Se criar a pasta (Processos › Área › Nome completo), responda "
            f"*PASTA D{codigo}* que eu guardo.")


def _hora_brt(g, ano, d):
    dia, mes, h, mi = (int(x) for x in g)
    return datetime(ano, mes, dia, h, mi, tzinfo=d.BRT).astimezone(timezone.utc)


def avisos_pendentes(msgs_adv, agora, d):
    """Avisos com código D dos últimos 7 dias e o que já aconteceu com cada um."""
    saida = []
    for i, m in enumerate(msgs_adv):
        txt = m.get("content") or ""
        cod, cab = RE_CODIGO_AVISO.search(txt), RE_CABECALHO.search(txt)
        if m.get("sender") == "CONTACT" or not cod or not cab:
            continue
        criado = d.ler_iso(m["createdAt"])
        if agora - criado > VALIDADE:
            continue
        ult, pri = RE_ULTIMO.search(txt), RE_PRIMEIRO.search(txt)
        if not ult:
            continue
        fim = _hora_brt(ult.groups(), criado.year, d)
        inicio = _hora_brt(pri.groups(), criado.year, d) if pri else fim
        if fim > criado + timedelta(days=1):  # aviso de 31/12 com arquivo de 01/01 não acontece; virada de ano
            fim, inicio = fim.replace(year=fim.year - 1), inicio.replace(year=inicio.year - 1)
        n = cod.group(1)
        depois = msgs_adv[i + 1:]
        marcas = [x for x in depois if x.get("sender") != "CONTACT"
                  and (RE_MARCA.match(x.get("content") or "") or [None, None, None])[2] == n]
        respostas = []
        for x in depois:
            r = RE_RESPOSTA.match(d.sem_acento(x.get("content") or "").lower()) if x.get("sender") == "CONTACT" else None
            if r and r.group(2) == n:
                respostas.append((x, bool(r.group(1)), r.group(3).strip()))
        criar = RE_CRIAR.search(txt)
        saida.append({"codigo": n, "nome": cab.group(1), "tel": cab.group(2), "criado": criado,
                      "de": inicio - timedelta(minutes=10), "ate": fim + timedelta(minutes=30),
                      "auto": "vou guardar em" in txt or bool(criar),
                      "area_criar": criar.group(1) if criar else None, "nome_criar": criar.group(2) if criar else None,
                      "ultima_marca": marcas[-1] if marcas else None, "respostas": respostas})
    return saida


def _ler_resto(resto):
    """'familia' -> ('FAMÍLIA', None); '2' -> (None, 2); '' -> (None, None)."""
    if re.fullmatch(r"\d{1,2}", resto):
        return None, int(resto)
    return AREAS.get(resto.replace(" ", "")), None


def executar(av, resto, adv, d):
    import agenda_google
    area, escolha = _ler_resto(resto)
    criar = bool(av["area_criar"])
    area_final = (area or av["area_criar"]) if criar else area
    r = agenda_google.guardar_arquivos(av["tel"], av["de"], av["ate"], nome_limpo(av["nome"], d), area=area_final,
                                       escolha=escolha, criar=criar,
                                       nome_pasta=nome_da_pasta(av["nome"], area_final, adv, d) if criar else "")
    c = f"*D{av['codigo']}*"
    st = (r or {}).get("status")
    if st == "movido" and r.get("n"):
        return (f"✅ {c} guardado: {r['n']} arquivo(s) em {r['caminho']}."
                + (" Pasta nova criada." if r.get("criada") else ""))
    if st == "movido":
        return (f"⚠️ {c}: a pasta é {r['caminho']}, mas os arquivos não estavam mais em \"Mídias - Whatsapp\" "
                f"(alguém já moveu ou foram para a lixeira). Nada foi mudado.")
    if st == "varias":
        opcoes = "\n".join(f"{i}) {x['caminho']}" for i, x in enumerate(r["candidatos"][:6], 1))
        return f"❓ {c}: achei mais de uma pasta:\n{opcoes}\nResponda *PASTA D{av['codigo']} 1* (ou o número certo)."
    if st == "sem_area":
        return f"❓ {c}: não existe a área \"{area_final}\" em Processos. Responda *PASTA D{av['codigo']}* com outra área."
    return (f"❓ {c}: não achei a pasta de {av['nome']} em Processos. Crie a pasta (Processos › Área › Nome completo) "
            f"e responda *PASTA D{av['codigo']}*.")


def decidir(av, agora):
    """(acao, resto, chave): acao 'guardar', 'nao', 'ja_guardado' ou None."""
    marca = av["ultima_marca"]
    guardado = bool(marca) and (marca.get("content") or "").startswith("✅")
    novas = [r for r in av["respostas"] if not marca or r[0]["createdAt"] > marca["createdAt"]]
    if novas:
        msg, nao, resto = novas[-1]
        chave = msg.get("id") or msg["createdAt"]
        if guardado:
            return ("ja_guardado" if nao else None), "", chave
        return ("nao" if nao else "guardar"), resto, chave
    if not marca and av["auto"] and agora - av["criado"] >= AUTO_APOS:
        return "guardar", "", "auto"
    return None, "", None


def rodada(zaia, agora, contagem, d):
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return
    _estado["ultima"] = agora
    import agenda_google
    if not agenda_google.configurado():
        return
    for adv in d.ADVOGADOS:
        conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=adv["tel"]) or {}).get("conversa")
        if not conv:
            continue
        msgs = sorted((zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []),
                      key=lambda m: m["createdAt"])
        for av in avisos_pendentes(msgs, agora, d):
            acao, resto, chave = decidir(av, agora)
            if not acao or (adv["tel"], av["codigo"], chave) in _feito:
                continue
            _feito.add((adv["tel"], av["codigo"], chave))
            c = f"*D{av['codigo']}*"
            if acao == "nao":
                texto = f"👍 {c}: combinado, não guardo estes arquivos na pasta."
            elif acao == "ja_guardado":
                texto = f"👍 {c}: os arquivos já estavam guardados. Se não quiser, é só apagar na pasta do Drive."
            else:
                if d.DRY_RUN:
                    d.log("[simulação] guardaria arquivos de cliente na pasta do Drive")
                    continue
                try:
                    texto = executar(av, resto, adv, d)
                except Exception as erro:
                    d.log(f"pasta do cliente falhou: {type(erro).__name__}")
                    _feito.discard((adv["tel"], av["codigo"], chave))  # tenta de novo na próxima volta
                    continue
            if d.DRY_RUN:
                continue
            zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"], texto=texto)
            contagem["pastas_cliente"] = contagem.get("pastas_cliente", 0) + 1
            d.log(f"arquivos de cliente: {texto[:2]} ({adv['curto']})")
