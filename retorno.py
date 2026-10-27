"""Retorno mensal aos clientes — sem IA.

Uma vez por dia útil, entre 9h e 11h (Belém), separa a fatia do dia dos clientes com
processo ativo no EasyJur (cada cliente cai num dia a cada 20 dias úteis, cerca de 4
semanas). Para cada cliente da fatia que não recebeu mensagem assinada por advogado nos
últimos 25 dias, manda ao advogado responsável, no privado, um rascunho de notícia
(itens T1, T2...). Nada vai ao cliente sem a ordem "CLIENTE T1" do advogado, que a
secretaria executa.

Gasto no EasyJur: 2 listagens de processos + 1 get_pessoa por cliente da fatia (~8 por dia);
a última movimentação já vem na listagem ("ultimo_andamento").
Privacidade: o log só leva contagens.
"""

import re
from datetime import date, datetime, timedelta, timezone

import secretaria
import telefones

BRT = timezone(timedelta(hours=-3))
CICLO = 20                              # dias úteis entre dois retornos do mesmo cliente
JANELA_CONTATO = timedelta(days=25)     # mensagem de advogado mais nova que isto: não precisa de retorno
HORA_INICIO, HORA_FIM = 9, 11
BASE = date(2026, 1, 5)                 # uma segunda-feira: início da contagem dos dias úteis
LIMITE_PARTE = 3500

ADVOGADOS = {
    344269: {"chave": "danielle", "nome": "Dra. Danielle", "tel": "5594992048054"},
    378457: {"chave": "fernanda", "nome": "Dra. Fernanda", "tel": "5594991742534"},
    344268: {"chave": "lucas", "nome": "Dr. Lucas", "tel": "5524992432455"},
}
PADRAO = 344269   # processo sem advogado, ou com estagiária/secretária como responsável

# Última movimentação ("10/09/2026 - Conclusos para julgamento") em linguagem de cliente.
FRASES = [
    (r"conclus", "o processo está com o juiz para análise e decisão"),
    (r"senten", "houve sentença no processo, e vamos te explicar os detalhes"),
    (r"acordao|recurso|turma|camara", "o processo está em fase de recurso, aguardando julgamento no tribunal"),
    (r"audiencia", "houve movimentação sobre a audiência, e vamos te orientar sobre os próximos passos"),
    (r"pericia|laudo|perito", "houve movimentação sobre a perícia"),
    (r"alvara|rpv|precatorio|pagamento|deposito|requisicao", "houve movimentação sobre o pagamento"),
    (r"contestac", "a outra parte apresentou a defesa dela"),
    (r"cita[cd]|intima", "as partes foram intimadas para se manifestar no processo"),
    (r"suspens|sobrest", "o processo está suspenso, aguardando outra decisão"),
    (r"arquiv", "o processo foi arquivado, e vamos te explicar o que isso significa"),
    (r"remet|distribu|redistribu", "o processo foi encaminhado ao setor responsável"),
    (r"decisao|despacho", "o juiz deu um despacho para o processo seguir"),
    (r"juntada|peticao|documento|manifestac|certid", "foram juntados documentos ao processo"),
]

_estado = {"feito": None}


def _log(msg):
    print(f"[{datetime.now(BRT):%d/%m %H:%M:%S}] retorno: {msg}", flush=True)


def dia_util_indice(d):
    semanas, resto = divmod((d - BASE).days, 7)
    return semanas * 5 + min(resto, 5)


def da_fatia(id_cliente, d):
    return int(id_cliente) % CICLO == dia_util_indice(d) % CICLO


def frase_processo(p):
    ultimo = (p.get("ultimo_andamento") or "").strip()
    if not ultimo:
        if p.get("tipo_processo") == "administrativo":
            return "o seu requerimento segue em análise no órgão"
        return "o processo segue em andamento normal"
    m = re.match(r"(\d{2}/\d{2}/\d{4})\s*-\s*(.*)", ultimo)
    quando, desc = (m.group(1), m.group(2)) if m else ("", ultimo)
    n = secretaria.norm(desc)
    frase = next((f for padrao, f in FRASES if re.search(padrao, n)), "houve uma movimentação de rotina")
    return f"a última movimentação foi em {quando}: {frase}" if quando else frase


def primeiro_nome(nome):
    return (nome or "").split()[0].capitalize() if (nome or "").split() else ""


def rascunho(nome, processos):
    if len(processos) == 1:
        p = processos[0]
        num = f" nº {p['numero']}" if p.get("numero") else ""
        corpo = f"Passando para dar notícias do seu processo{num}: {frase_processo(p)}."
    else:
        partes = [f"no nº {p.get('numero') or '(sem número)'}, {frase_processo(p)}" for p in processos[:3]]
        corpo = "Passando para dar notícias dos seus processos: " + "; ".join(partes) + "."
    return (f"Olá, {primeiro_nome(nome)}! {corpo} Seguimos acompanhando de perto e avisamos assim que "
            f"houver novidade. Qualquer dúvida, é só responder esta mensagem.")


def telefone(ej, id_cliente):
    p = (ej.chamar("get_pessoa", pessoa_id=int(id_cliente)) or {}).get("data") or {}
    return telefones.do_cadastro(p)


def teve_contato(zaia, tel, agora):
    """True se um advogado mandou mensagem assinada a este cliente nos últimos 25 dias."""
    conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=tel) or {}).get("conversa")
    if not conv:
        return False
    ultima = conv.get("lastMessageAt")
    if ultima and agora - secretaria.ler_iso(ultima) > JANELA_CONTATO:
        return False
    for m in (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []):
        if m.get("sender") == "CONTACT" or agora - secretaria.ler_iso(m["createdAt"]) > JANELA_CONTATO:
            continue
        if any(re.match(r"^\*?\s*dra?\.?\s", secretaria.norm(t))
               for t in (m.get("content"), secretaria.sem_assinatura(m.get("content")))):
            return True  # "*Annie*:\n*Dra. Fernanda Mesquita:*\n..." (CLIENTE) ou "*Dra Danielle Esteves*:" (painel)
    return False


def ja_enviado_hoje(zaia, adv, hoje):
    conv = (zaia.chamar("buscar_conversa_por_telefone", telefone=adv["tel"]) or {}).get("conversa")
    if not conv:
        return False
    for m in (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", []):
        if (m.get("sender") != "CONTACT" and secretaria.sem_assinatura(m.get("content")).startswith(secretaria.INICIO_RETORNO)
                and secretaria.ler_iso(m["createdAt"]).astimezone(BRT).date() == hoje):
            return True
    return False


def mensagens(adv, itens):
    """Texto ao advogado, em partes de até 3.500 caracteres sem quebrar item."""
    blocos = []
    for i, (nome, tel, procs) in enumerate(itens, 1):
        nums = ", ".join(p.get("numero") or "(sem número)" for p in procs[:3])
        blocos.append(f"T{i}. *{nome}* — {nums}\n   📲 Para o cliente *{primeiro_nome(nome)}* (📞 {tel}):\n"
                      f"   \"{rascunho(nome, procs)}\"")
    rodape = ("_Responda:_ *CLIENTE T1 T3* envia o rascunho · *CLIENTE T2: seu texto* envia o seu texto · "
              "*CLIENTE T TODOS* envia todos. Sem resposta, nada é enviado.")
    intro = (f"_{adv['nome']}, estes clientes têm processo ativo e não recebem mensagem de advogado há mais "
             f"de 25 dias. Rascunhos de notícia:_")
    partes, atual = [], [intro]
    for b in blocos:
        if len("\n\n".join(atual + [b])) > LIMITE_PARTE and len(atual) > 1:
            partes.append(atual)
            atual = []
        atual.append(b)
    partes.append(atual + [rodape])
    n = len(partes)
    titulo = secretaria.INICIO_RETORNO + " aos clientes*"
    return [(f"{titulo} ({k}/{n})" if n > 1 else titulo) + "\n" + "\n\n".join(p) for k, p in enumerate(partes, 1)]


def rodada(zaia, ej_fn, agora=None, contagem=None):
    agora = agora or datetime.now(timezone.utc)
    contagem = contagem if contagem is not None else {}
    local = agora.astimezone(BRT)
    hoje = local.date()
    if local.weekday() >= 5 or not HORA_INICIO <= local.hour < HORA_FIM or _estado["feito"] == hoje:
        return
    _estado["feito"] = hoje  # uma tentativa por plantão e por dia, mesmo se falhar (poupa a cota)
    ej = ej_fn()
    if secretaria.e_feriado(ej, hoje):
        return
    processos = []
    for pagina in range(1, 6):
        r = ej.chamar("list_processos", status="1", page_size=100, page=pagina) or {}
        processos += r.get("data") or []
        if pagina >= int((r.get("meta") or {}).get("total_pages") or 1):
            break
    por_cliente = {}
    for p in processos:
        if p.get("id_cliente") and da_fatia(p["id_cliente"], hoje):
            por_cliente.setdefault(p["id_cliente"], []).append(p)
    por_adv, sem_tel, recentes = {}, 0, 0
    for cid, procs in por_cliente.items():
        tel = telefone(ej, cid)
        if not tel:
            sem_tel += 1
            continue
        if teve_contato(zaia, tel, agora):
            recentes += 1
            continue
        resp = [p.get("id_advogado") for p in procs if p.get("id_advogado") in ADVOGADOS]
        adv = max(set(resp), key=resp.count) if resp else PADRAO
        nome = (procs[0].get("nome_cliente") or "").strip().title()
        por_adv.setdefault(adv, []).append((nome, tel, procs))
    for adv_id, itens in por_adv.items():
        adv = ADVOGADOS[adv_id]
        if ja_enviado_hoje(zaia, adv, hoje):
            continue
        for texto in mensagens(adv, itens):
            zaia.chamar("enviar_mensagem", assinatura="ia", numero=adv["tel"], texto=texto)
        contagem["retornos_propostos"] = contagem.get("retornos_propostos", 0) + len(itens)
    _log(f"fatia de hoje: {len(por_cliente)} cliente(s); propostos {sum(len(v) for v in por_adv.values())}, "
         f"com contato recente {recentes}, sem celular {sem_tel}")
