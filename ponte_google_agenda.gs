/**
 * Ponte do despachante com o Google Agenda do escritório — Esteves Advocacia.
 *
 * Roda DENTRO da conta Google do escritório (script.google.com), publicado como
 * "App da Web". O despachante (GitHub) chama este endereço para criar a reunião
 * no Google Agenda, com link do Google Meet, e recebe o link de volta.
 *
 * Segurança: só responde a quem mandar a CHAVE gravada nas propriedades do
 * script (rode a função configurar() uma vez; ela cria a chave e mostra no
 * registro). Nenhuma senha do Google sai daqui.
 *
 * Chamada aberta: a sala do Meet nasce pela API do Google Meet já com acesso
 * ABERTO (quem tem o link entra sem pedir permissão) e é presa ao evento da
 * agenda. O Google não deixa abrir depois uma sala criada pela própria Agenda
 * (caso de 28/10). Se a API falhar, cai na sala normal da Agenda (aberta=false).
 * A API do Meet precisa estar ativada no projeto do Google Cloud ligado ao
 * script ("Ponte Agenda Escritorio", criado em 28/10).
 */

var CALENDARIO = 'primary';  // agenda principal da conta que instala o script
var FUSO = 'America/Belem';

function configurar() {
  var props = PropertiesService.getScriptProperties();
  var chave = props.getProperty('CHAVE');
  if (!chave) {
    chave = Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, '');
    props.setProperty('CHAVE', chave);
  }
  Logger.log('Copie esta chave para o segredo GOOGLE_AGENDA_CHAVE do GitHub: ' + chave);
  // Força a autorização de todas as permissões na primeira execução.
  CalendarApp.getDefaultCalendar();
  UrlFetchApp.getRequest('https://meet.googleapis.com/v2/spaces');
}

/** Teste à mão no editor: cria uma sala e mostra se ela nasceu aberta. */
function testarSalaAberta() {
  var sala = criarSalaAberta();
  Logger.log(sala ? 'sala ' + sala.meetingUri + ' com acesso ' + sala.config.accessType : 'a API do Meet recusou');
}

function doPost(e) {
  try {
    var p = JSON.parse(e.postData.contents);
    if (p.chave !== PropertiesService.getScriptProperties().getProperty('CHAVE')) {
      return saida({ ok: false, erro: 'chave inválida' });
    }
    if (p.acao === 'criar') return saida(criar(p));
    if (p.acao === 'buscar') return saida(buscar(p));
    if (p.acao === 'teste') return saida({ ok: true, calendario: CALENDARIO });
    return saida({ ok: false, erro: 'ação desconhecida' });
  } catch (err) {
    return saida({ ok: false, erro: String(err).slice(0, 300) });
  }
}

function saida(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** Procura evento já existente no dia com o nome do lead no título (evita duplicar). */
function buscar(p) {
  var inicioDia = new Date(p.dia + 'T00:00:00-03:00');
  var fimDia = new Date(p.dia + 'T23:59:59-03:00');
  var itens = Calendar.Events.list(CALENDARIO, {
    timeMin: inicioDia.toISOString(), timeMax: fimDia.toISOString(), singleEvents: true, q: p.nome
  }).items || [];
  var achados = itens.filter(function (ev) { return ev.status !== 'cancelled'; }).map(function (ev) {
    var local = ev.location || '';
    return { id: ev.id, titulo: ev.summary, inicio: ev.start.dateTime,
             link: ev.hangoutLink || (local.indexOf('meet.google.com') >= 0 ? local : '') };
  });
  return { ok: true, eventos: achados };
}

/** Cria a reunião com Meet; convida o advogado (se vier e-mail); tenta abrir a sala. */
function criar(p) {
  var existentes = buscar({ dia: p.inicio.slice(0, 10), nome: p.nome }).eventos.filter(function (ev) {
    return ev.inicio && ev.inicio.slice(11, 16) === p.inicio.slice(11, 16);
  });
  if (existentes.length) {
    return { ok: true, id: existentes[0].id, link: existentes[0].link, ja_existia: true, aberta: null };
  }
  var evento = {
    summary: p.titulo,
    description: p.descricao || '',
    location: 'Online',
    start: { dateTime: p.inicio, timeZone: FUSO },
    end: { dateTime: p.fim, timeZone: FUSO },
    reminders: { useDefault: false, overrides: [
      { method: 'popup', minutes: 1440 }, { method: 'popup', minutes: 60 }, { method: 'email', minutes: 60 }
    ] },
    conferenceData: { createRequest: { requestId: Utilities.getUuid(),
                                       conferenceSolutionKey: { type: 'hangoutsMeet' } } }
  };
  if (p.convidado) evento.attendees = [{ email: p.convidado }];
  var sala = criarSalaAberta();
  var criado = null;
  if (sala) {
    evento.location = sala.meetingUri;
    evento.conferenceData = { conferenceId: sala.meetingCode, conferenceSolution: { key: { type: 'hangoutsMeet' } },
                              entryPoints: [{ entryPointType: 'video', uri: sala.meetingUri,
                                              label: sala.meetingUri.replace('https://', '') }] };
    try {
      criado = Calendar.Events.insert(evento, CALENDARIO, { conferenceDataVersion: 1, sendUpdates: 'all' });
    } catch (err) {  // a Agenda recusou prender a sala: o link vai só no local do evento
      delete evento.conferenceData;
      criado = Calendar.Events.insert(evento, CALENDARIO, { sendUpdates: 'all' });
    }
    return { ok: true, id: criado.id, link: sala.meetingUri, ja_existia: false, aberta: true };
  }
  criado = Calendar.Events.insert(evento, CALENDARIO, { conferenceDataVersion: 1, sendUpdates: 'all' });
  var link = criado.hangoutLink || '';
  for (var i = 0; !link && i < 5; i++) {  // o Meet às vezes leva alguns segundos para ficar pronto
    Utilities.sleep(1500);
    criado = Calendar.Events.get(CALENDARIO, criado.id);
    link = criado.hangoutLink || '';
  }
  return { ok: true, id: criado.id, link: link, ja_existia: false, aberta: abrirSala(link) };
}

/** Cria a sala pela API do Meet já ABERTA. Devolve a sala ({meetingUri, meetingCode, config}) ou null. */
function criarSalaAberta() {
  try {
    var r = UrlFetchApp.fetch('https://meet.googleapis.com/v2/spaces', {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      payload: JSON.stringify({ config: { accessType: 'OPEN' } })
    });
    if (r.getResponseCode() !== 200) {
      Logger.log('Meet recusou a sala: ' + r.getResponseCode() + ' ' + r.getContentText().slice(0, 300));
      return null;
    }
    var sala = JSON.parse(r.getContentText());
    return sala.meetingUri && sala.config && sala.config.accessType === 'OPEN' ? sala : null;
  } catch (err) {
    Logger.log('Meet falhou: ' + String(err).slice(0, 300));
    return null;
  }
}

/**
 * Limpeza da pasta "Mídias - Whatsapp" (pedido da usuária, 29/10): a integração do Drive da Za.Ia salva TODA mídia
 * que chega no WhatsApp, numa subpasta por telefone. A rotina Pós-reunião move os arquivos de cliente para
 * Processos › Área › Nome; o que sobra aqui há mais de DIAS_MIDIAS dias vai para a LIXEIRA (o Google guarda 30 dias).
 * A folga cobre documento mandado antes da assinatura, que a rotina só move depois. Pastas de cliente nunca são tocadas.
 */
var PASTA_MIDIAS = '1x8EkMbdFFHt8Bl4uF-QRHxi8t9jfbYH8';
var DIAS_MIDIAS = 7;

function limparMidias() {
  var limite = new Date(Date.now() - DIAS_MIDIAS * 864e5);
  var raiz = DriveApp.getFolderById(PASTA_MIDIAS);
  var pastas = [raiz], n = 0;
  var subs = raiz.getFolders();
  while (subs.hasNext()) pastas.push(subs.next());
  pastas.forEach(function (pasta) {
    var arqs = pasta.getFiles();
    while (arqs.hasNext()) {
      var a = arqs.next();
      if (a.getDateCreated() < limite) { a.setTrashed(true); n++; }
    }
  });
  Logger.log(n + ' arquivo(s) com mais de ' + DIAS_MIDIAS + ' dias foram para a lixeira');
}

/** Rode uma vez no editor: agenda limparMidias todo dia às 21h (depois da última rodada da Pós-reunião). */
function instalarLimpeza() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'limparMidias') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('limparMidias').timeBased().everyDays(1).atHour(21).inTimezone(FUSO).create();
  limparMidias();
}

/** Reserva: tenta abrir uma sala já existente (o Google só deixa nas salas criadas pela API). */
function abrirSala(link) {
  if (!link) return false;
  var codigo = link.split('/').pop();
  try {
    var r = UrlFetchApp.fetch('https://meet.googleapis.com/v2/spaces/' + codigo + '?updateMask=config.accessType', {
      method: 'patch', contentType: 'application/json', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
      payload: JSON.stringify({ config: { accessType: 'OPEN' } })
    });
    return r.getResponseCode() === 200;
  } catch (err) {
    return false;
  }
}

/** Teste à mão no editor: cria um evento de teste amanhã às 23h, mostra o link e apaga o evento. */
function testarCriarEvento() {
  var amanha = Utilities.formatDate(new Date(Date.now() + 86400000), FUSO, 'yyyy-MM-dd');
  var r = criar({ titulo: 'TESTE sala aberta (apagar)', nome: 'TESTE sala aberta', inicio: amanha + 'T23:00:00',
                  fim: amanha + 'T23:30:00', descricao: 'teste' });
  var ev = Calendar.Events.get(CALENDARIO, r.id);
  Logger.log(JSON.stringify({ link: r.link, aberta: r.aberta, linkDaAgenda: ev.hangoutLink || '', local: ev.location }));
  Calendar.Events.remove(CALENDARIO, r.id);
}
