"""Secretaria sem IA — executa os comandos de formato fixo que os advogados mandam no WhatsApp.

Roda dentro do plantão do despachante, a cada 2 minutos. Não usa nenhuma IA.

1. COMANDOS DO RESUMO MATINAL (Dra. Fernanda e Dra. Danielle), em resposta à
   mensagem "*Bom dia, Dra. ...*" que traz os itens numerados com 🔖:
     LIDA 1 3 A2 · LIDA TODAS · MANTER 2 · PRAZO 2 13/10 [texto] ·
     TAREFA 4 05/10 texto · AGENDAR 10/10 14h assunto · MINHA AGENDA · AGENDA Lucas
2. APROVAÇÕES DO RELATÓRIO "📋 PENDÊNCIAS DR. LUCAS" (17h30):
     OK 2 · OK 1 3 · OK TODAS · EDITAR 2: texto · NÃO 2

Qualquer outra mensagem é ignorada (fica para as rotinas com IA). Cada comando
é executado uma vez só: a resposta do escritório leva a marca "#<id da
mensagem do comando>", e o programa procura essa marca antes de agir.

Privacidade: o log nunca leva nome, telefone nem texto de conversa.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
LUCAS_CONTROLADORIA = 344268

ADVOGADAS_RESUMO = [
    {"chave": "fernanda", "nome": "Dra. Fernanda", "tel": "5594991742534", "id": 378457},
    {"chave": "danielle", "nome": "Dra. Danielle", "tel": "5594992048054", "id": 344269},
]
DR_LUCAS = {"chave": "lucas", "nome": "Dr. Lucas", "tel": "5524992432455", "id": 344268,
            "assinatura": "*Dr. Lucas:*", "etiqueta": "PENDÊNCIA LUCAS"}
AGENDA_POR_NOME = {"danielle": 344269, "dani": 344269, "fernanda": 378457,
                   "lucas": 344268, "diva": 372515}

COMECO = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)  # nada anterior à entrada no ar
INTERVALO = timedelta(minutes=2)
JANELA_COMANDO = timedelta(hours=24)
JANELA_RELATORIO = timedelta(hours=48)
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

_estado = {"ultima": None, "visto": {}}   # visto: telefone -> lastMessageAt já processado
_feitos = set()  # ids das mensagens de comando já executadas neste plantão (segunda trava contra repetição)
_feriados = {}


def _log(msg):
    print(f"[{datetime.now(BRT):%d/%m %H:%M:%S}] secretaria: {msg}", flush=True)


def norm(t):
    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower().strip()


def ler_iso(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def marca(msg):
    """Marca curta, única por mensagem de comando, posta na resposta do escritório."""
    return "#" + re.sub(r"\D", "", msg.get("id", ""))[-8:]


# ------------------------------------------------------------------ datas
def data_br(txt, hoje):
    """'14/10' ou '14/10/2026' -> date. Sem ano: este ano, ou o próximo se já passou."""
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", txt)
    if not m:
        return None
    d, mo, a = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if a:
            a = int(a) + (2000 if len(a) == 2 else 0)
            return date(a, mo, d)
        dt = date(hoje.year, mo, d)
        return dt if dt >= hoje - timedelta(days=1) else date(hoje.year + 1, mo, d)
    except ValueError:
        return None


RE_HORA = re.compile(r"(?<![\d/])(\d{1,2})(?:[:h](\d{2})|h)(?![\d/])", re.I)


def horas(txt):
    """Hora de início e de fim (se houver 'até') citadas no texto, sem confundir com a data."""
    sem_data = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", txt)
    achadas = []
    for m in RE_HORA.finditer(sem_data):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if h < 24 and mi < 60:
            achadas.append(f"{h:02d}:{mi:02d}")
    if not achadas:
        return None, None
    fim = achadas[1] if len(achadas) > 1 and re.search(r"\bate\b|\s-\s", norm(sem_data)) else None
    return achadas[0], fim


def mais_uma_hora(h):
    hh, mm = map(int, h.split(":"))
    return f"{min(hh + 1, 23):02d}:{mm:02d}"


def e_feriado(ej, d):
    if d not in _feriados:
        r = ej.chamar("e_feriado", data=d.isoformat()) or {}
        _feriados[d] = bool((r.get("data") or {}).get("e_feriado"))
    return _feriados[d]


def dias_uteis_antes(ej, d, n, hoje):
    x, contados = d, 0
    while contados < n:
        x -= timedelta(days=1)
        if x.weekday() < 5 and not e_feriado(ej, x):
            contados += 1
    return max(x, hoje)


def ddmm(d):
    return f"{d:%d/%m}"


# ------------------------------------------------------------------ resumo matinal
RE_ITEM = re.compile(r"^\s*\*?((?:[AM])?\d{1,3})\.\s*\*?\s*(.*)$")
RE_REF = re.compile(r"🔖\s*([PAE])-([0-9A-Za-z.,\- ]+)")
RE_PROC = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


def itens_do_resumo(texto):
    """{'1': {'ref': ('P', '7925421011'), 'processo': '...'}, 'A1': {...}}"""
    itens, atual = {}, None
    for linha in texto.splitlines():
        m = RE_ITEM.match(linha)
        if m:
            atual = m.group(1).upper()
            proc = RE_PROC.search(m.group(2))
            itens[atual] = {"ref": None, "processo": proc.group(0) if proc else ""}
            continue
        r = RE_REF.search(linha)
        if r and atual and itens[atual]["ref"] is None:
            itens[atual]["ref"] = (r.group(1), r.group(2).strip().rstrip("."))
    return {k: v for k, v in itens.items() if v["ref"]}


def resumo_vigente(msgs, antes_de):
    """Junta as partes (1/n) do resumo matinal mais recente enviado antes do comando."""
    resumos = [m for m in msgs if m.get("sender") != "CONTACT"
               and (m.get("content") or "").startswith("*Bom dia, Dra.") and "🔖" in (m.get("content") or "")
               and m["createdAt"] < antes_de]
    if not resumos:
        return None, {}
    ultimo = ler_iso(resumos[-1]["createdAt"])
    partes = [m for m in resumos if ultimo - ler_iso(m["createdAt"]) < timedelta(minutes=30)]
    if datetime.now(timezone.utc) - ultimo > timedelta(days=4):
        return None, {}
    texto = "\n".join(m["content"] for m in partes)
    return ultimo, itens_do_resumo(texto)


RE_LISTA_ITENS = re.compile(r"\b([am]?\d{1,3})\b", re.I)


def classificar_linha(linha):
    """Devolve (comando, resto) se a linha está num dos formatos aceitos; senão None."""
    n = norm(linha).rstrip(".!")
    if n in ("minha agenda",):
        return ("MINHA AGENDA", "")
    m = re.match(r"^agenda\s+(?:da |do |de )?(?:dra?\.?\s+)?(\w+)$", n)
    if m and m.group(1) in AGENDA_POR_NOME:
        return ("AGENDA", m.group(1))
    m = re.match(r"^(lidas?|lido)\s+(.+)$", n)
    if m and (m.group(2).startswith("todas") or RE_LISTA_ITENS.search(m.group(2))):
        return ("LIDA", m.group(2))
    m = re.match(r"^manter\s+(.+)$", n)
    if m and RE_LISTA_ITENS.search(m.group(1)):
        return ("MANTER", m.group(1))
    m = re.match(r"^(prazo|tarefa)\s+([am]?\d{1,3})[\s,]+(.*)$", n)
    if m and re.search(r"\b\d{1,2}/\d{1,2}", m.group(3)):
        return (m.group(1).upper(), linha.strip())
    if re.match(r"^(agendar|agende|agenda)\b", n) and re.search(r"\b\d{1,2}/\d{1,2}", n):
        return ("AGENDAR", linha.strip())
    return None


def itens_citados(resto):
    resto = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", resto)
    return [x.upper() for x in RE_LISTA_ITENS.findall(resto)]


class Execucao:
    """Executa os comandos de uma advogada e junta as linhas de resposta."""

    def __init__(self, ej_fn, adv, hoje, itens):
        self.ej_fn, self.adv, self.hoje, self.itens, self.linhas = ej_fn, adv, hoje, itens, []

    @property
    def ej(self):
        return self.ej_fn()

    def item(self, num):
        it = self.itens.get(num)
        if not it:
            self.linhas.append(f"❓ Não achei o item {num} no resumo mais recente.")
        return it

    def marcar_lida(self, num, it):
        tipo, ref = it["ref"]
        rotulo = f"item {num} — {it['processo'] or ref}"
        if tipo == "P":
            r = self.ej.chamar("list_publicacoes", codPublicacao=ref, page_size=5) or {}
            pubs = r.get("data") or []
            if not pubs:
                self.linhas.append(f"⚠️ Não achei a publicação do {rotulo} no EasyJur.")
                return
            p = pubs[0]
            self.ej.chamar("atualizar_leitura_publicacao", publicacao_id=int(p["id"]), lida=True,
                           marcar_relacionadas=True)
            if p.get("numProcesso") and p.get("dataPublicacao"):
                dia = str(p["dataPublicacao"])[:10]
                copias = (self.ej.chamar("list_publicacoes", numProcesso=p["numProcesso"], status="A",
                                         data_inicio=dia, data_fim=dia, page_size=20) or {}).get("data") or []
                for c in copias:
                    if c.get("id") != p.get("id"):
                        self.ej.chamar("atualizar_leitura_publicacao", publicacao_id=int(c["id"]), lida=True)
            self.linhas.append(f"✅ Lida: {rotulo}")
        elif tipo == "A":
            for i in re.findall(r"\d+", ref):
                self.ej.chamar("update_andamento", andamento_id=int(i), body={"status": "Lido"})
            self.linhas.append(f"✅ Lida: {rotulo}")
        else:
            self.linhas.append(f"✅ Ciente: {rotulo} (só no PJe)")

    def processo_do_item(self, it):
        tipo, ref = it["ref"]
        try:
            if tipo == "P":
                p = (self.ej.chamar("get_publicacao", publicacao_id=ref) or {}).get("data") or {}
                proc = p.get("processo") or {}
                return proc.get("id"), p
            if tipo == "A":
                a = (self.ej.chamar("get_andamento", andamento_id=int(re.findall(r"\d+", ref)[0])) or {}).get("data") or {}
                return a.get("id_processo") or (a.get("processo") or {}).get("id"), None
            r = (self.ej.chamar("list_processos", numero=ref, page_size=2) or {}).get("data") or []
            return (r[0]["id"] if len(r) == 1 else None), None
        except Exception:
            return None, None

    def lida(self, resto):
        nums = list(self.itens) if norm(resto).startswith("todas") else itens_citados(resto)
        for num in nums:
            it = self.item(num)
            if it:
                self.marcar_lida(num, it)

    def manter(self, resto):
        for num in itens_citados(resto):
            it = self.item(num)
            if it:
                tipo, ref = it["ref"]
                self.linhas.append(f"📌 Mantido: item {num} — {it['processo'] or ref} 🔖 {tipo}-{ref}")

    def prazo_ou_tarefa(self, cmd, linha):
        m = re.match(r"^\s*\w+\s+([AaMm]?\d{1,3})[\s,]+(.*)$", linha)
        num, resto = m.group(1).upper(), m.group(2)
        it = self.item(num)
        fatal = data_br(resto, self.hoje)
        if not it:
            return
        if not fatal:
            self.linhas.append(f"❓ Não entendi a data: {linha.strip()[:60]}. Exemplo: {cmd} 2 13/10")
            return
        texto = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", "", resto).strip(" ,.-")
        proc_id, pub = self.processo_do_item(it)
        tipo, ref = it["ref"]
        args = {"id_advogado": self.adv["id"], "data_fim": fatal.isoformat(), "processo": proc_id}
        if cmd == "PRAZO":
            interno = dias_uteis_antes(self.ej, fatal, 2, self.hoje)
            args.update(tipo="PRAZO", id_advogado2=LUCAS_CONTROLADORIA, data=interno.isoformat(),
                        descricao=(texto or f"Prazo — item {num} ({it['processo'] or ref})") + " (criado pelo WhatsApp)")
            if tipo == "P":
                args.update(codigo_publicacao=ref,
                            data_publicacao=str((pub or {}).get("dataPublicacao") or "")[:10] or None)
        else:
            args.update(tipo="TAREFA", data=fatal.isoformat(),
                        descricao=(texto or f"Tarefa — item {num}") + " (criado pelo WhatsApp)")
        r = self.ej.chamar("create_agenda", **args) or {}
        novo = (r.get("data") or {}).get("id") if isinstance(r, dict) else None
        aviso = "" if proc_id else " ⚠️ sem vínculo com processo (não achei no EasyJur)"
        if cmd == "PRAZO":
            self.marcar_lida(num, it)
            self.linhas.pop()  # a linha "Lida" fica implícita no prazo
            self.linhas.append(f"✅ Prazo criado: item {num} — {it['processo'] or ref} — fatal {ddmm(fatal)}, "
                               f"interno {ddmm(interno)}{aviso} (id {novo})")
        else:
            self.linhas.append(f"✅ Tarefa criada: item {num} — {ddmm(fatal)}{aviso} (id {novo})")

    def agendar(self, linha):
        dia = data_br(linha, self.hoje)
        ini, fim = horas(linha)
        assunto = re.sub(r"^\s*(agendar|agende|agenda)\b(\s+na minha agenda)?", "", linha, flags=re.I)
        assunto = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}(?:[:h]\d{2}|h)\b", " ", assunto)
        assunto = re.sub(r"\b(?:item\s*)?\d{1,3}\s*,|\b(hoje|amanh[ãa]|para o dia|no dia|dia|às|as|das|até|ate|de)\b",
                         " ", assunto, flags=re.I)
        assunto = re.sub(r"(?i)\b(dra?\.?\s*)?(fernanda|danielle|dani)\b\s*,?", " ", assunto)
        assunto = re.sub(r"(?i)assunto\s*:", " ", assunto)
        assunto = re.sub(r"\s+", " ", assunto).strip(" ,.:-") or "Compromisso"
        if not dia:
            self.linhas.append("❓ Não entendi a data. Exemplo: AGENDAR 10/10 14h assunto")
            return
        if not ini:
            self.linhas.append(f"❓ Qual horário para \"{assunto[:50]}\" em {ddmm(dia)}? "
                               f"Exemplo: AGENDAR {ddmm(dia)} 14h {assunto[:30]}")
            return
        a = norm(assunto)
        tipo = ("AUDIENCIA" if "audiencia" in a else "PERICIA" if "pericia" in a else
                "REUNIAO" if "reuniao" in a else "ATENDIMENTO" if ("atendimento" in a or "consulta" in a)
                else "TAREFA")
        r = self.ej.chamar("create_agenda", tipo=tipo, id_advogado=self.adv["id"], data=dia.isoformat(),
                           data_fim=dia.isoformat(), hora_inicio=ini, hora_fim=fim or mais_uma_hora(ini),
                           descricao=assunto + " (criado pelo WhatsApp)") or {}
        novo = (r.get("data") or {}).get("id") if isinstance(r, dict) else None
        extra = (" ℹ️ Gravei só no EasyJur; para o Google Agenda, peça ao assistente em texto livre."
                 if "google" in norm(linha) else "")
        self.linhas.append(f"📅 Agendado: {DIAS_SEMANA[dia.weekday()]} {ddmm(dia)} {ini.replace(':', 'h')} — "
                           f"{assunto} ({tipo.lower()}, id {novo}){extra}")

    def agenda(self, quem_id, titulo):
        fim = self.hoje + timedelta(days=1)
        itens = (self.ej.chamar("list_agenda", id_responsavel_qualquer=quem_id, data_interna_inicio=self.hoje.isoformat(),
                                data_interna_fim=fim.isoformat(), page_size=100, ordenacao="1") or {}).get("data") or []
        itens = [i for i in itens if i.get("status") in ("A", "N", "P")]
        if not itens:
            self.linhas.append(f"📅 {titulo}: nada para hoje e amanhã.")
            return
        linhas = [f"📅 {titulo} (hoje e amanhã):"]
        for i in sorted(itens, key=lambda i: (str(i.get("data")), str(i.get("hora_inicio")))):
            h = str(i.get("hora_inicio") or "")[:5]
            h = "" if h in ("", "00:00") else " " + h.replace(":", "h")
            desc = re.sub(r"\s+", " ", str(i.get("descricao") or ""))[:70]
            cli = (i.get("nome_cliente") or "").strip()
            linhas.append(f"• {str(i.get('data'))[8:10]}/{str(i.get('data'))[5:7]}{h} · {i.get('tipo', '').lower()}"
                          f"{' · ' + cli if cli else ''} · {desc}")
        self.linhas.append("\n".join(linhas))


def comandos_do_resumo(zaia, ej_fn, adv, msgs, agora, contagem):
    ja = "\n".join(m.get("content") or "" for m in msgs if m.get("sender") != "CONTACT")
    hoje = agora.astimezone(BRT).date()
    for m in msgs:
        if m.get("sender") != "CONTACT" or m.get("contentType") not in (None, "CHAT", "TEXT"):
            continue
        quando = ler_iso(m["createdAt"])
        if quando < COMECO or agora - quando > JANELA_COMANDO or marca(m) in ja or m["id"] in _feitos:
            continue
        linhas = [(l, classificar_linha(l)) for l in (m.get("content") or "").splitlines() if l.strip()]
        linhas = [(l, c) for l, c in linhas if c]
        if not linhas:
            continue
        _, itens = resumo_vigente(msgs, m["createdAt"])
        _feitos.add(m["id"])
        exe = Execucao(ej_fn, adv, hoje, itens)
        for linha, (cmd, resto) in linhas:
            try:
                if cmd in ("LIDA", "MANTER", "PRAZO", "TAREFA") and not itens:
                    exe.linhas.append(f"❓ Não achei resumo recente para \"{linha.strip()[:40]}\".")
                elif cmd == "LIDA":
                    exe.lida(resto)
                elif cmd == "MANTER":
                    exe.manter(resto)
                elif cmd in ("PRAZO", "TAREFA"):
                    exe.prazo_ou_tarefa(cmd, linha)
                elif cmd == "AGENDAR":
                    exe.agendar(linha)
                elif cmd == "MINHA AGENDA":
                    exe.agenda(adv["id"], "Sua agenda")
                elif cmd == "AGENDA":
                    exe.agenda(AGENDA_POR_NOME[resto], f"Agenda de {resto.capitalize()}")
            except Exception as erro:
                if type(erro).__name__ == "OrcamentoEasyJur":
                    raise
                exe.linhas.append(f"⚠️ Não consegui executar \"{linha.strip()[:40]}\": {str(erro)[:120]}")
        if exe.linhas:
            zaia.chamar("enviar_mensagem", numero=adv["tel"], texto="\n".join(exe.linhas) + f"\n_{marca(m)}_")
            contagem["comandos"] = contagem.get("comandos", 0) + len(linhas)
            _log(f"{len(linhas)} comando(s) executado(s) para {adv['chave']}")


# ------------------------------------------------------------------ pendências do Dr. Lucas
# "*2) MARIA* — 📞 5594..." (a rotina às vezes escreve "*[2]) MARIA*")
RE_BLOCO = re.compile(r"\*\[?(\d{1,2})\]?\)\s*([^*]+)\*\s*[—–-]\s*📞\s*\+?(\d{10,13})")
RE_SUGESTAO = re.compile(r"✍️\s*Sugest[aã]o:\s*\"(.*?)\"(.*)$", re.S)


def relatorio_lucas(msgs, antes_de):
    rel = [m for m in msgs if m.get("sender") != "CONTACT" and "PENDÊNCIAS DR. LUCAS" in (m.get("content") or "")[:60]
           and m["createdAt"] < antes_de]
    if not rel:
        return None, {}
    ultimo = ler_iso(rel[-1]["createdAt"])
    texto = "\n".join(m["content"] for m in rel if ultimo - ler_iso(m["createdAt"]) < timedelta(minutes=15))
    itens = {}
    blocos = RE_BLOCO.split(texto)
    # split devolve [antes, num, nome, tel, corpo, num, nome, tel, corpo, ...]
    for i in range(1, len(blocos) - 3, 4):
        num, nome, tel, corpo = blocos[i], blocos[i + 1].strip(), blocos[i + 2], blocos[i + 3]
        s = RE_SUGESTAO.search(corpo.split("━━")[0])
        if s:
            texto_sug = s.group(1).strip()
            itens[num] = {"nome": nome, "tel": tel, "texto": texto_sug,
                          "alerta": "⚠️" in s.group(2).split("\n")[0] or "⟨" in texto_sug}
    # sugestões novas geradas a partir de áudio substituem a do item
    for m in msgs:
        t = m.get("content") or ""
        n = re.search(r"Nova sugest[aã]o (\d{1,2})\*.*?\n\"(.*?)\"", t, re.S)
        if m.get("sender") != "CONTACT" and n and ler_iso(m["createdAt"]) > ultimo and n.group(1) in itens:
            itens[n.group(1)].update(texto=n.group(2).strip(), alerta="⟨" in n.group(2))
    return ultimo, itens


def ordens_lucas(texto):
    """Lista de (acao, numero, texto_editado) na ordem em que aparecem."""
    ordens, edit = [], None
    for linha in texto.splitlines():
        n = norm(linha)
        m_ok = re.match(r"^ok\s+(todas|todos|[\d\s,e]+)\.?$", n)
        m_nao = re.match(r"^nao\s+(\d{1,2})\.?$", n)
        m_ed = re.match(r"^\s*editar\s+(\d{1,2})\s*[:\-]\s*(.*)$", linha, re.I)
        if m_ok or m_nao or m_ed:
            if edit:
                ordens.append(edit)
                edit = None
        if m_ok:
            alvo = m_ok.group(1)
            if alvo.startswith("tod"):
                ordens.append(("OK", "TODAS", None))
            else:
                ordens += [("OK", x, None) for x in re.findall(r"\d{1,2}", alvo)]
        elif m_nao:
            ordens.append(("NAO", m_nao.group(1), None))
        elif m_ed:
            edit = ("EDITAR", m_ed.group(1), m_ed.group(2))
        elif edit:
            edit = (edit[0], edit[1], (edit[2] + "\n" + linha).strip())
    if edit:
        ordens.append(edit)
    return [(a, n, (t or "").strip() or None) for a, n, t in ordens]


def tirar_etiqueta(zaia, tel, nome_etiqueta):
    contatos = (zaia.chamar("buscar_contatos", query=tel, limit=3) or {}).get("contatos") or []
    for c in contatos:
        if re.sub(r"\D", "", c.get("phone") or "") != tel:
            continue
        for lab in c.get("labels") or []:
            if norm(lab.get("name")) == norm(nome_etiqueta):
                zaia.chamar("remover_etiqueta_contato", contatoId=c["id"], etiquetaId=lab["id"])


def aprovacoes_lucas(zaia, msgs, agora, contagem, enviar=True):
    ja = "\n".join(m.get("content") or "" for m in msgs if m.get("sender") != "CONTACT")
    for m in msgs:
        if m.get("sender") != "CONTACT" or m.get("contentType") not in (None, "CHAT", "TEXT"):
            continue
        quando = ler_iso(m["createdAt"])
        if quando < COMECO or agora - quando > JANELA_COMANDO or marca(m) in ja or m["id"] in _feitos:
            continue
        ordens =ordens_lucas(m.get("content") or "")
        if not ordens:
            continue
        rel_em, itens = relatorio_lucas(msgs, m["createdAt"])
        if not rel_em or quando - rel_em > JANELA_RELATORIO:
            continue  # "OK 2" sem relatório recente não é para cá
        _feitos.add(m["id"])
        linhas = []
        if any(a == "OK" and n == "TODAS" for a, n, _ in ordens):
            ordens = [o for o in ordens if o[1] != "TODAS"] + [("OK", k, None) for k, v in itens.items()
                                                                if not v["alerta"]]
        for acao, num, texto in ordens:
            it = itens.get(num)
            if not it:
                linhas.append(f"❓ Não achei o item {num} no relatório de pendências.")
                continue
            if acao == "NAO":
                linhas.append(f"⏭️ Item {num} não enviado")
                continue
            texto = texto if acao == "EDITAR" else (None if it["alerta"] else it["texto"])
            if not texto:
                linhas.append(f"❓ Item {num} tem um trecho para completar ⟨…⟩. Responda EDITAR {num}: seu texto")
                continue
            if "⟨" in texto:
                linhas.append(f"❓ O texto do item {num} ainda tem ⟨ ⟩. Corrija com EDITAR {num}: texto")
                continue
            if enviar:
                zaia.chamar("enviar_mensagem", numero=it["tel"], texto=f"{DR_LUCAS['assinatura']}\n{texto}")
                try:
                    tirar_etiqueta(zaia, it["tel"], DR_LUCAS["etiqueta"])
                except Exception as erro:  # etiqueta não pode impedir a confirmação
                    _log(f"etiqueta não retirada: {type(erro).__name__}")
            linhas.append(f"✅ Enviado para {it['nome']} (item {num})")
            contagem["respostas_lucas"] = contagem.get("respostas_lucas", 0) + 1
        if linhas:
            zaia.chamar("enviar_mensagem", numero=DR_LUCAS["tel"], texto="\n".join(linhas) + f"\n_{marca(m)}_")
            _log(f"{len(ordens)} ordem(ns) do relatório de pendências tratada(s)")


# ------------------------------------------------------------------ rodada
def rodada(zaia, ej_fn, agora=None, contagem=None):
    """Chamada pelo despachante a cada minuto; trabalha no máximo a cada 2 minutos."""
    agora = agora or datetime.now(timezone.utc)
    contagem = contagem if contagem is not None else {}
    lidas = {}  # telefone -> mensagens baixadas nesta rodada (o porteiro reaproveita)
    if _estado["ultima"] and agora - _estado["ultima"] < INTERVALO:
        return lidas
    _estado["ultima"] = agora
    for adv, tarefa in [(a, "resumo") for a in ADVOGADAS_RESUMO] + [(DR_LUCAS, "lucas")]:
        try:
            conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=adv["tel"]) or {}).get("conversa")
            if not conv:
                continue
            chave = adv["tel"] + tarefa
            if _estado["visto"].get(chave) == conv.get("lastMessageAt"):
                continue  # nada novo desde a última leitura: não baixa a conversa inteira
            msgs = sorted((zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []),
                          key=lambda x: x["createdAt"])
            lidas[adv["tel"]] = msgs
            if tarefa == "resumo":
                comandos_do_resumo(zaia, ej_fn, adv, msgs, agora, contagem)
            else:
                aprovacoes_lucas(zaia, msgs, agora, contagem)
            _estado["visto"][chave] = conv.get("lastMessageAt")
        except Exception as erro:
            if type(erro).__name__ == "OrcamentoEasyJur":
                raise
            _log(f"falhou ({adv['chave']}): {type(erro).__name__}")
    return lidas
