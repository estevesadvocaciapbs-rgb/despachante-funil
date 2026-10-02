"""Despachante do funil — Esteves Advocacia.

Roda sem IA, de poucos em poucos minutos, e faz duas coisas:

1. OFERTA: para cada lead triado que ainda não recebeu oferta, consulta a
   agenda do advogado no EasyJur e agenda no WhatsApp do lead a mensagem com
   2 horários livres — o mais próximo de manhã e o mais próximo à tarde.
2. CONFIRMAÇÃO: quando a Annie confirma ao lead o horário escolhido
   ("...ficou marcado para..."), grava a reunião no EasyJur (pessoa,
   oportunidade e ATENDIMENTO), agenda o lembrete de 1 hora antes e avisa o
   grupo "Firma 2026", só para conhecimento, com o resumo do caso e o horário.

Os leads triados são lidos das TAREFAS da Za.Ia (último passo dos roteiros em
"Criar tarefa") e, enquanto os roteiros antigos existirem, também dos
resumos que chegam ao grupo.

Casos que pedem julgamento (atendimento incompleto, criminal urgente, filtro
de viabilidade trabalhista, lead já atendido por alguém da equipe) ficam com as
rotinas com IA.

Credenciais só por variável de ambiente: ZAIA_TOKEN e EASYJUR_TOKEN.
Uso:  python despachante.py            (executa)
      python despachante.py --dry-run  (só mostra o que faria, não grava nem envia)
      python despachante.py --vigia    (plantão: uma rodada por minuto até as 21h)
"""

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

ZAIA_URL = "https://mcp.zaials.com.br/mcp"
EASYJUR_URL = "https://api.easyjur.com/mcp"
GRUPO = "claude-grupo-1"
BRT = timezone(timedelta(hours=-3))
DRY_RUN = "--dry-run" in sys.argv
THALYTA = 354290

DANIELLE = {"id": 344269, "nome": "A Dra. Danielle Esteves", "curto": "Dra. Danielle Esteves",
            "inicios": ["10:00", "10:30", "11:00", "14:00", "14:30", "15:00",
                        "15:30", "16:00", "16:30", "17:00"]}
FERNANDA = {"id": 378457, "nome": "A Dra. Fernanda Mesquita", "curto": "Dra. Fernanda Mesquita",
            "inicios": ["09:30", "14:30"], "bloqueia_dia_audiencia": True}
LUCAS = {"id": 344268, "nome": "O Dr. Lucas", "curto": "Dr. Lucas",
         "inicios": ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00",
                     "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30"]}
ADVOGADOS = [DANIELLE, FERNANDA, LUCAS]

TIPOS_QUE_OCUPAM = {"ATENDIMENTO", "AUDIENCIA", "REUNIAO", "PERICIA", "DILIGENCIA",
                    "VIAGEM", "EVENTOS", "JULGAMENTO", "CONSULTORIA", "LIGACAO",
                    "PARTICULAR", "PRIVADO"}
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
DURACAO_MIN = 30
ANTECEDENCIA_H = 3
DIAS_UTEIS_JANELA = 5
JANELA_LEAD_H = 48
JANELA_CONFIRMACAO_D = 7
OFERTA_RESERVA_H = 3
MARCA_OFERTA = "Tenho estes horários"
MARCA_CONFIRMACAO = "ficou marcado para"

EQUIPE = set(filter(None, os.environ.get(
    "TELEFONES_EQUIPE", "").replace(" ", "").split(",")))


def log(msg):
    # Nunca registra nome, telefone ou conteúdo de conversa (o log do GitHub é público).
    print(f"[{datetime.now(BRT):%d/%m %H:%M:%S}] {msg}", flush=True)


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn").lower()


def ler_iso(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


# ---------------------------------------------------------------- cliente MCP
class MCP:
    def __init__(self, url, token, nome):
        if not token:
            raise SystemExit(f"Falta a variável de ambiente do token de {nome}.")
        self.url, self.token, self.nome = url, token, nome
        self.sessao, self.seq = None, 0
        self._post({"jsonrpc": "2.0", "id": self._id(), "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                               "clientInfo": {"name": "despachante-funil", "version": "2.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, espera=False)

    def _id(self):
        self.seq += 1
        return self.seq

    def _post(self, corpo, espera=True):
        cab = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "Authorization": f"Bearer {self.token}"}
        if self.sessao:
            cab["Mcp-Session-Id"] = self.sessao
        req = urllib.request.Request(self.url, data=json.dumps(corpo).encode(), headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.headers.get("Mcp-Session-Id"):
                    self.sessao = r.headers["Mcp-Session-Id"]
                bruto = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{self.nome}: HTTP {e.code}") from None
        if not espera or not bruto.strip():
            return None
        if bruto.lstrip().startswith("{"):
            return json.loads(bruto)
        ultimo = None  # resposta em SSE
        for linha in bruto.splitlines():
            if linha.startswith("data:"):
                try:
                    ultimo = json.loads(linha[5:].strip())
                except ValueError:
                    pass
        return ultimo

    def chamar(self, ferramenta, **args):
        args = {k: v for k, v in args.items() if v is not None}
        resp = self._post({"jsonrpc": "2.0", "id": self._id(), "method": "tools/call",
                           "params": {"name": ferramenta, "arguments": args}})
        if not resp or "error" in resp:
            raise RuntimeError(f"{self.nome}.{ferramenta}: erro na chamada")
        res = resp.get("result", {})
        if res.get("isError"):
            raise RuntimeError(f"{self.nome}.{ferramenta}: a ferramenta devolveu erro")
        texto = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        try:
            return json.loads(texto)
        except ValueError:
            return texto


# ---------------------------------------------------------------- leitura dos leads
RE_CONTATO_GRUPO = re.compile(r"Contato\s*-\s*\*([^*]+)\*\s*\((\d{10,13})\)")
RE_LEAD = re.compile(r"(?:LEAD|CONTATO):\s*([^\n(]+?)\s*\((\d{10,13})\)")
RE_CONTATO_TAREFA = re.compile(r"Contato:\s*([^\n(]+?)\s*\((\d{10,13})\)")
RE_DEPARTAMENTO = re.compile(r"Departamento:\s*(\S+)")
DEPARTAMENTOS_CLIENTE = {"suporte", "acompanhamento_de_clientes", "recepcao",
                         "atendimento-reclamada", "licenca-maternidade-decisao-do-stf"}


def eh_briefing(texto):
    sa = sem_acento(texto)
    return any(k in sa for k in ("nova oportunidade", "novo lead", "atendimento incompleto"))


def resumo_do_caso(texto):
    """Extrai o resumo do briefing, sem cabeçalhos nem o raciocínio interno da tarefa."""
    corpo = texto.split("Resumo do atendimento:")[0]
    linhas = []
    for l in corpo.splitlines():
        s = l.strip()
        if not s or s.startswith(("Contato -", "LEAD:", "CONTATO:", "ÁREA:", "AREA:",
                                  "RESPONSÁVEL:", "RESPONSAVEL:", "‼", "*🆕", "🆕", "🔔",
                                  "Dados coletados", "Departamento:")):
            continue
        if re.match(r"^[a-z_]+:\s", s):  # campos salvos (salario_atrasado: sim ...)
            continue
        linhas.append(s)
    texto = " ".join(linhas)
    return (texto[:700] + "…") if len(texto) > 700 else texto


def leads_recentes(grupo, tarefas, agora):
    leads = {}

    def guardar(nome, tel, texto, quando, origem):
        if tel in EQUIPE or agora - quando > timedelta(hours=JANELA_LEAD_H):
            return
        atual = leads.get(tel)
        if not atual or quando > atual["quando"] or (origem == "tarefa" and atual["origem"] == "grupo"):
            leads[tel] = {"nome": nome.strip(), "tel": tel, "texto": texto,
                          "quando": quando, "origem": origem}

    for t in tarefas:
        texto = f"{t.get('title', '')}\n{t.get('description', '')}"
        dep = RE_DEPARTAMENTO.search(texto)
        if dep and dep.group(1) in DEPARTAMENTOS_CLIENTE:
            continue
        if not eh_briefing(texto):
            continue
        achado = RE_CONTATO_TAREFA.search(texto) or RE_LEAD.search(texto)
        if achado:
            guardar(achado.group(1), achado.group(2), texto, ler_iso(t["createdAt"]), "tarefa")

    for m in grupo.get("mensagens", []):
        txt = m.get("content", "")
        if m.get("sender") != "AGENT" or not eh_briefing(txt) or "Oferta de horários" in txt:
            continue
        achado = RE_CONTATO_GRUPO.search(txt) or RE_LEAD.search(txt)
        if achado:
            guardar(achado.group(1), achado.group(2), txt, ler_iso(m["createdAt"]), "grupo")
    return list(leads.values())


def classificar(texto):
    """Devolve (area, motivo_para_pular)."""
    sa_todo = sem_acento(texto)
    if "atendimento incompleto" in sa_todo:
        return None, "incompleto"
    if "urgente" in sa_todo:
        return None, "urgente"
    linha = re.search(r"(?:area:|novo lead\s*[·\-—]+)\s*([^\n*]+)", sa_todo)
    sa = linha.group(1) if linha else sa_todo
    if "licenca-maternidade" in sa or "licenca maternidade" in sa:
        return None, "informativo"
    if "violencia domestica" in sa:
        return "vd", None
    if "familia" in sa:
        return "familia", None
    if "criminal" in sa or "penal" in sa:
        return "criminal", None
    if "previdenci" in sa:
        return "previdenciario", None
    if "trabalhista" in sa or "rescisao indireta" in sa:
        return "trabalhista", None
    if any(k in sa for k in ("civel", "consumidor", "tributari", "juros", "revisao contratual")):
        return "civel", None
    return None, "area_incerta"


NOME_AREA = {"vd": "Família — Violência Doméstica", "familia": "Família", "criminal": "Criminal",
             "previdenciario": "Previdenciário", "trabalhista": "Trabalhista",
             "civel": "Cível / Consumidor / Tributário"}


def pediu_fernanda(texto):
    sa = sem_acento(texto)
    return "pedido do cliente" in sa and "fernanda" in sa


def reprova_viabilidade(texto):
    """Filtro de entrada do POP: experiência até 45 dias (exceto gestante)."""
    sa = sem_acento(texto)
    if any(k in sa for k in ("gestante", "gravida", "gravidez")) or "experiencia" not in sa:
        return False
    return any(int(n) <= 45 for n in re.findall(r"(\d{1,3})\s*dias", sa))


# ---------------------------------------------------------------- agenda
class Agenda:
    def __init__(self, easyjur, agora):
        self.ej, self.agora, self.feriados = easyjur, agora, {}

    def e_feriado(self, d):
        if d not in self.feriados:
            r = self.ej.chamar("e_feriado", data=d.isoformat())
            self.feriados[d] = bool((r or {}).get("data", {}).get("e_feriado"))
        return self.feriados[d]

    def dias_possiveis(self):
        # a partir do próximo dia útil (nunca o próprio dia do contato)
        dias, d = [], self.agora.date() + timedelta(days=1)
        while len(dias) < DIAS_UTEIS_JANELA and d <= self.agora.date() + timedelta(days=21):
            if d.weekday() <= 3 and not self.e_feriado(d):  # segunda a quinta
                dias.append(d)
            d += timedelta(days=1)
        return dias

    def itens(self, adv_id, inicio, fim, tipo=None):
        todos, pag = [], 1
        while True:
            r = self.ej.chamar("list_agenda", id_responsavel_qualquer=adv_id, tipo=tipo,
                               data_interna_inicio=inicio.isoformat(),
                               data_interna_fim=fim.isoformat(), page=pag, page_size=100)
            todos += r.get("data", [])
            if pag >= r.get("meta", {}).get("total_pages", 1):
                return todos
            pag += 1

    def livres(self, adv, reservados):
        dias = self.dias_possiveis()
        if not dias:
            return []
        ocupado, dia_bloqueado = {}, set()
        for it in self.itens(adv["id"], dias[0], dias[-1]):
            if it.get("status") == "S":
                continue
            tipo = (it.get("tipo") or "").upper()
            d0 = date.fromisoformat(it["data"])
            d1 = date.fromisoformat(it.get("data_fim") or it["data"])
            sem_hora = (it.get("hora_inicio") or "00:00:00")[:5] == "00:00"
            if adv.get("bloqueia_dia_audiencia") and tipo == "AUDIENCIA":
                dia_bloqueado.add(d0)
            if tipo not in TIPOS_QUE_OCUPAM:
                continue
            if sem_hora:
                if tipo == "VIAGEM":
                    d = d0
                    while d <= d1:
                        dia_bloqueado.add(d)
                        d += timedelta(days=1)
                continue
            h0 = datetime.strptime(it["hora_inicio"][:5], "%H:%M")
            hf = (it.get("hora_fim") or "00:00:00")[:5]
            h1 = datetime.strptime(hf, "%H:%M") if hf != "00:00" else h0 + timedelta(hours=1)
            if h1 <= h0:
                h1 = h0 + timedelta(hours=1)
            ocupado.setdefault(d0, []).append((h0.time(), h1.time()))
        limite = self.agora + timedelta(hours=ANTECEDENCIA_H)
        saida = []
        for d in dias:
            if d in dia_bloqueado:
                continue
            for hhmm in adv["inicios"]:
                ini = datetime.combine(d, datetime.strptime(hhmm, "%H:%M").time(), BRT)
                fim = ini + timedelta(minutes=DURACAO_MIN)
                if ini < limite or (adv["id"], ini) in reservados:
                    continue
                if any(ini.time() < b and fim.time() > a for a, b in ocupado.get(d, [])):
                    continue
                saida.append(ini)
        return saida


def manha_e_tarde(slots):
    """O horário livre mais próximo de manhã e o mais próximo à tarde.

    Como os dias começam no próximo dia útil, os dois saem desse dia; se um
    turno estiver lotado nele, vem do dia útil seguinte que tiver o turno livre.
    """
    manha = next((s for s in slots if s.hour < 12), None)
    tarde = next((s for s in slots if s.hour >= 12), None)
    escolhidos = sorted(s for s in (manha, tarde) if s)
    if len(escolhidos) < 2:  # só há um turno livre: completa com o próximo horário
        escolhidos = sorted(set(escolhidos) | set(slots[:2]))[:2]
    return escolhidos


def texto_slot(s):
    return f"{DIAS_SEMANA[s.weekday()]}, {s:%d/%m}, às {s:%H}h{s:%M}"


RE_SLOT = re.compile(r"(\d{2})/(\d{2}),? às (\d{1,2})h(\d{2})")


def data_do_texto(dd, mm, hh, mi, agora):
    ano = agora.year + (1 if int(mm) < agora.month - 6 else 0)
    return datetime(ano, int(mm), int(dd), int(hh), int(mi), tzinfo=BRT)


def advogado_do_texto(txt):
    return DANIELLE if "Danielle" in txt else FERNANDA if "Fernanda" in txt else LUCAS


def reservas_recentes(agendamentos, agora):
    reservados = set()
    for a in agendamentos:
        txt = a.get("content") or ""
        if MARCA_OFERTA not in txt or agora - ler_iso(a["scheduledAt"]) > timedelta(hours=OFERTA_RESERVA_H):
            continue
        adv = advogado_do_texto(txt)
        for dd, mm, hh, mi in RE_SLOT.findall(txt):
            reservados.add((adv["id"], data_do_texto(dd, mm, hh, mi, agora)))
    return reservados


def id_de(resposta):
    if isinstance(resposta, dict):
        dado = resposta.get("data") if isinstance(resposta.get("data"), dict) else resposta
        return dado.get("id")
    return None


def primeiro_nome(nome):
    p = re.split(r"\s+", nome.strip())[0] if nome.strip() else ""
    return p[:1].upper() + p[1:].lower() if p else ""


# ---------------------------------------------------------------- etapa 1: oferta
def ofertar(zaia, agenda_fn, leads, agendamentos, agora, contagem):
    reservados = reservas_recentes(agendamentos, agora)
    for lead in leads:
        area, pular = classificar(lead["texto"])
        if not pular and area == "trabalhista" and reprova_viabilidade(lead["texto"]):
            pular = "viabilidade"
        if pular:
            contagem["pulados"] += 1
            log(f"lead pulado ({pular}) — fica com a rotina com IA")
            continue
        conv = zaia.chamar("buscar_conversa_por_telefone", telefone=lead["tel"]).get("conversa")
        if not conv:
            continue
        contato_id = conv["contact"]["id"]
        if any(a.get("contactId") == contato_id and MARCA_OFERTA in (a.get("content") or "")
               for a in agendamentos):
            continue
        msgs = zaia.chamar("ler_conversa", conversaId=conv["id"]).get("messages", [])
        if any(MARCA_OFERTA in m.get("content", "") or MARCA_CONFIRMACAO in m.get("content", "")
               for m in msgs):
            continue
        depois = [m for m in msgs if ler_iso(m["createdAt"]) >= lead["quando"] - timedelta(minutes=5)]
        if any(m.get("sender") == "USER" for m in depois):
            contagem["pulados"] += 1
            log("lead pulado (alguém da equipe já está atendendo)")
            continue
        if area == "criminal" and re.search(r"\b(pres[oa]|depoimento|audiencia)\b",
                                           sem_acento(" ".join(m.get("content", "") for m in msgs))):
            contagem["pulados"] += 1
            log("lead pulado (criminal com possível urgência) — fica com a rotina com IA")
            continue

        agenda = agenda_fn()
        if pediu_fernanda(lead["texto"]) or area in ("familia", "vd", "criminal"):
            candidatos = [FERNANDA]
        elif area == "trabalhista":
            candidatos = [DANIELLE, FERNANDA]
        elif area == "civel":
            candidatos = [LUCAS]
        else:
            candidatos = [DANIELLE, FERNANDA, LUCAS]

        adv, slots = None, []
        for c in candidatos:
            livres = agenda.livres(c, reservados)
            if not livres:
                continue
            if area == "previdenciario" and not pediu_fernanda(lead["texto"]):
                if not slots or livres[0] < slots[0]:
                    adv, slots = c, livres
            else:
                adv, slots = c, livres
                break

        if not slots:
            contagem["sem_horario"] += 1
            grupo = zaia.chamar("ler_grupo", grupoId=GRUPO, limit=60)
            ja = any("SEM HORÁRIO DISPONÍVEL" in m.get("content", "") and lead["tel"] in m.get("content", "")
                     for m in grupo.get("mensagens", []))
            if not ja and not DRY_RUN:
                zaia.chamar("enviar_mensagem_grupo", grupoId=GRUPO, texto=(
                    f"⚠️ *SEM HORÁRIO DISPONÍVEL — {lead['nome']} ({lead['tel']})*\n"
                    f"{NOME_AREA.get(area, '')}. Não há horário livre nos próximos {DIAS_UTEIS_JANELA} "
                    "dias úteis. 👉 Equipe: abrir um horário e combinar com o lead.\n"
                    f"*Caso:* {resumo_do_caso(lead['texto'])}"))
            log("sem horário livre — avisado no grupo")
            continue

        dois = manha_e_tarde(slots)
        lista = "; ".join(f"{i}) {texto_slot(s)}" for i, s in enumerate(dois, 1))
        oferta = (f"Olá, {primeiro_nome(lead['nome'])}! {adv['nome']} analisou o seu caso e pode te "
                  f"atender por videochamada. {MARCA_OFERTA}: {lista}. Qual fica melhor pra você?")
        if DRY_RUN:
            log(f"[simulação] ofereceria 2 horários ({adv['curto']})")
            print("    " + oferta)
        else:
            quando = (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:00.000Z")
            zaia.chamar("agendar_mensagem", contatoId=contato_id, conversaId=conv["id"],
                        mensagem=oferta, dataHora=quando, assinatura="ia", ativarIaAoResponder=True)
            if area == "vd":
                zaia.chamar("enviar_mensagem_grupo", grupoId=GRUPO, texto=(
                    f"🚨 *PRIORIDADE — VIOLÊNCIA DOMÉSTICA — {lead['nome']} ({lead['tel']})*\n"
                    f"Horários mais próximos da Dra. Fernanda oferecidos: {lista}.\n"
                    "👉 Equipe: acompanhar e, se houver risco imediato, contatar a cliente agora."))
            log(f"oferta agendada ({adv['curto']})")
        for s in dois:
            reservados.add((adv["id"], s))
        contagem["ofertas"] += 1


# ---------------------------------------------------------------- etapa 2: confirmação
def confirmar(zaia, easyjur_fn, agenda_fn, leads, enviados, pendentes, agora, contagem):
    resumos = {l["tel"]: l for l in leads}
    vistos = set()
    for a in enviados:
        txt = a.get("content") or ""
        if MARCA_OFERTA not in txt or a.get("contactId") in vistos:
            continue
        if agora - ler_iso(a["scheduledAt"]) > timedelta(days=JANELA_CONFIRMACAO_D):
            continue
        vistos.add(a.get("contactId"))
        conv_id = a.get("conversationId")
        if not conv_id:
            continue
        conversa = zaia.chamar("ler_conversa", conversaId=conv_id)
        msgs = sorted(conversa.get("messages", []), key=lambda m: m["createdAt"])
        conf = [m for m in msgs if m.get("sender") == "AGENT" and MARCA_CONFIRMACAO in m.get("content", "")
                and ler_iso(m["createdAt"]) >= ler_iso(a["scheduledAt"])]
        if not conf:
            continue
        ultima = conf[-1]["content"]
        achado = RE_SLOT.search(ultima.split(MARCA_CONFIRMACAO, 1)[1])
        if not achado:
            continue
        inicio = data_do_texto(*achado.groups(), agora)
        if inicio < agora:
            continue
        adv = advogado_do_texto(ultima) if any(n in ultima for n in ("Danielle", "Fernanda", "Lucas")) \
            else advogado_do_texto(txt)
        contato = conversa.get("contact", {})
        nome, tel = contato.get("name", "").strip(), contato.get("phone", "")

        ej = easyjur_fn()
        agenda = agenda_fn()
        existentes = agenda.itens(adv["id"], inicio.date(), inicio.date(), tipo="ATENDIMENTO")
        if any((i.get("hora_inicio") or "")[:5] == f"{inicio:%H:%M}" and i.get("status") != "S"
               for i in existentes):
            continue  # já gravado (pela equipe, pelo auditor ou numa rodada anterior)
        livres = agenda.livres(adv, set())
        lead = resumos.get(tel, {})
        area, _ = classificar(lead.get("texto", ""))
        resumo = resumo_do_caso(lead.get("texto", "")) or "ver a conversa no WhatsApp."
        if inicio not in livres:
            if not DRY_RUN:
                zaia.chamar("enviar_mensagem_grupo", grupoId=GRUPO, texto=(
                    f"⚠️ *CONFLITO DE AGENDA — {nome} ({tel})*\nEscolheu {texto_slot(inicio)} com "
                    f"{adv['curto']}, que foi ocupado depois da oferta. 👉 Equipe: oferecer outro horário."))
            contagem["conflitos"] += 1
            log("conflito de agenda — avisado no grupo")
            continue
        if DRY_RUN:
            log(f"[simulação] gravaria reunião no EasyJur ({adv['curto']}) e avisaria o grupo")
            contagem["reunioes"] += 1
            continue

        pessoas = ej.chamar("list_pessoas", nome=nome, page_size=20).get("data", [])
        mesma = [p for p in pessoas if (p.get("nome") or "").strip().lower() == nome.lower()
                 and (p.get("celular") or "").replace(" ", "") in ("", tel, tel[2:])]
        if len(mesma) == 1:
            pessoa_id = mesma[0]["id"]
        else:
            pessoa_id = id_de(ej.chamar("create_pessoa", nome=nome, fisica_juridica="F", celular=tel,
                                        tipos=["lead"]))
        oport = ej.chamar("create_oportunidade", nome=f"{NOME_AREA.get(area, 'Atendimento')} — {nome}"[:100],
                          status="1", responsavel=adv["id"], responsavel2=THALYTA, cliente=pessoa_id,
                          data_atendimento=inicio.date().isoformat(), descricao=resumo)
        oport_id = id_de(oport)
        fim = inicio + timedelta(minutes=DURACAO_MIN)
        ej.chamar("create_agenda", tipo="ATENDIMENTO", id_advogado=adv["id"], id_advogado2=THALYTA,
                  cliente=pessoa_id, oportunidade=oport_id, data=inicio.date().isoformat(),
                  data_fim=inicio.date().isoformat(), hora_inicio=f"{inicio:%H:%M}", hora_fim=f"{fim:%H:%M}",
                  local="Online", descricao=f"Reunião com lead — {nome} ({tel}). Agendada automaticamente "
                  f"pela Annie. {resumo}")
        lembrete = inicio - timedelta(hours=1)
        tem_pendente = any(p.get("contactId") == a.get("contactId") for p in pendentes)
        if lembrete - agora > timedelta(minutes=10) and not tem_pendente:
            zaia.chamar("agendar_mensagem", contatoId=a["contactId"], conversaId=conv_id,
                        dataHora=lembrete.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:00.000Z"),
                        assinatura="ia", ativarIaAoResponder=True, mensagem=(
                            f"Olá, {primeiro_nome(nome)}! Passando para confirmar nosso atendimento de hoje "
                            f"às {inicio:%H}h{inicio:%M} com {adv['nome'][0].lower()}{adv['nome'][1:]}. "
                            "Podemos confirmar sua presença?"))
        zaia.chamar("enviar_mensagem_grupo", grupoId=GRUPO, texto=(
            f"📅 *REUNIÃO AGENDADA — {nome} ({tel})*\n"
            f"{adv['curto']} · {NOME_AREA.get(area, 'área a confirmar')} · {texto_slot(inicio)} · Online · "
            "já está na agenda do EasyJur\n"
            f"*Caso:* {resumo}\n_(aviso só para conhecimento)_"))
        contagem["reunioes"] += 1
        log(f"reunião gravada e grupo avisado ({adv['curto']})")


# ---------------------------------------------------------------- principal
def main():
    agora = datetime.now(BRT)
    zaia = MCP(ZAIA_URL, os.environ.get("ZAIA_TOKEN"), "Za.Ia")
    grupo = zaia.chamar("ler_grupo", grupoId=GRUPO, limit=80)
    tarefas = zaia.chamar("listar_tarefas", limit=100).get("tarefas", [])
    pendentes = zaia.chamar("listar_agendamentos", status="PENDING", limit=50).get("agendamentos", [])
    enviados = zaia.chamar("listar_agendamentos", status="SENT", limit=50).get("agendamentos", [])
    leads = leads_recentes(grupo, tarefas, agora)
    log(f"leads triados nas últimas {JANELA_LEAD_H} h: {len(leads)}")

    cache = {}

    def easyjur_fn():
        if "ej" not in cache:
            cache["ej"] = MCP(EASYJUR_URL, os.environ.get("EASYJUR_TOKEN"), "EasyJur")
        return cache["ej"]

    def agenda_fn():
        if "ag" not in cache:
            cache["ag"] = Agenda(easyjur_fn(), agora)
        return cache["ag"]

    contagem = {"ofertas": 0, "pulados": 0, "sem_horario": 0, "reunioes": 0, "conflitos": 0}
    ofertar(zaia, agenda_fn, leads, pendentes + enviados, agora, contagem)
    confirmar(zaia, easyjur_fn, agenda_fn, leads, enviados, pendentes, agora, contagem)
    log(f"resumo: {contagem}")


def vigia(minutos, intervalo_s=60, hora_fim=21):
    """Fica de plantão: roda uma rodada por minuto até o fim do turno.

    O agendador do GitHub atrasa e não roda em menos de 5 minutos; um job só,
    acordado, checando a cada 60 s, deixa a oferta sair em até ~2 minutos.
    """
    import time
    fim = time.monotonic() + minutos * 60
    while time.monotonic() < fim and datetime.now(BRT).hour < hora_fim:
        try:
            main()
        except Exception as erro:
            log(f"rodada falhou: {type(erro).__name__}: {erro}")
        time.sleep(intervalo_s)
    log("plantão encerrado")


if __name__ == "__main__":
    if "--vigia" in sys.argv:
        minutos = int(os.environ.get("VIGIA_MINUTOS", "345"))
        vigia(minutos)
        sys.exit(0)
    try:
        main()
    except Exception as erro:
        log(f"falhou: {type(erro).__name__}: {erro}")
        sys.exit(1)
