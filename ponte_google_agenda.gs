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
 * Chamada aberta: depois de criar o evento, tenta deixar a sala do Meet com
 * acesso ABERTO (quem tem o link entra sem pedir permissão), pela API do
 * Google Meet. Se a conta não permitir, devolve aberta=false e o link continua
 * valendo com as regras normais.
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
    return { id: ev.id, titulo: ev.summary, inicio: ev.start.dateTime, link: ev.hangoutLink || '' };
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
  var criado = Calendar.Events.insert(evento, CALENDARIO, { conferenceDataVersion: 1, sendUpdates: 'all' });
  var link = criado.hangoutLink || '';
  for (var i = 0; !link && i < 5; i++) {  // o Meet às vezes leva alguns segundos para ficar pronto
    Utilities.sleep(1500);
    criado = Calendar.Events.get(CALENDARIO, criado.id);
    link = criado.hangoutLink || '';
  }
  return { ok: true, id: criado.id, link: link, ja_existia: false, aberta: abrirSala(link) };
}

/** Acesso ABERTO na sala do Meet: quem tem o link entra sem pedir para entrar. */
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
