/**
 * Ponte Gmail - distribuições (25/11/2026) — Esteves Advocacia.
 *
 * Script SEPARADO da ponte da Agenda, de propósito: a leitura de Gmail é uma permissão "restrita" do Google e,
 * no projeto do Google Cloud da ponte da Agenda, o Google bloqueia. Aqui o script usa o projeto padrão do
 * Apps Script, que só mostra o aviso "app não verificado" (Avançado → Acessar).
 *
 * O que faz: lê no Gmail do escritório os e-mails "Push" do PJe com o evento de distribuição (TRT, TJ, TRF)
 * e devolve o texto para o despachante cadastrar no EasyJur o processo que ninguém cadastrou.
 * Só LEITURA (gmail.readonly). Publicado como App da Web: executar como eu, acesso "qualquer pessoa".
 *
 * Segurança: usa a MESMA chave da ponte da Agenda (segredo GOOGLE_AGENDA_CHAVE do GitHub). Aqui fica só a
 * impressão digital SHA-256 da chave (HASH_CHAVE), nunca a chave. Na cópia do GitHub o valor fica vazio.
 */
var HASH_CHAVE = '';

function doPost(e) {
  try {
    var p = JSON.parse(e.postData.contents);
    if (!HASH_CHAVE || sha256(p.chave || '') !== HASH_CHAVE) return saida({ ok: false, erro: 'chave inválida' });
    if (p.acao === 'distribuicoes') return saida(distribuicoes(p));
    if (p.acao === 'teste') return saida({ ok: true });
    return saida({ ok: false, erro: 'ação desconhecida' });
  } catch (err) {
    return saida({ ok: false, erro: String(err).slice(0, 300) });
  }
}

function saida(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function sha256(texto) {
  var b = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, texto, Utilities.Charset.UTF_8);
  return b.map(function (x) { return ('0' + (x & 255).toString(16)).slice(-2); }).join('');
}

var GMAIL = 'https://gmail.googleapis.com/gmail/v1/users/me/messages';

function distribuicoes(p) {
  var dias = Math.min(Math.max(Number(p.dias) || 5, 1), 15);
  var q = 'newer_than:' + dias + 'd ("Distribuído por" OR "Distribuido por" OR "Tipo de Distribuição")';
  var cab = { headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() } };
  var lista = JSON.parse(UrlFetchApp.fetch(GMAIL + '?maxResults=50&q=' + encodeURIComponent(q), cab).getContentText());
  var mensagens = (lista.messages || []).map(function (m) {
    var msg = JSON.parse(UrlFetchApp.fetch(GMAIL + '/' + m.id + '?format=full', cab).getContentText());
    return { id: m.id, texto: textoDe(msg.payload).slice(0, 8000) };
  });
  return { ok: true, mensagens: mensagens };
}

function textoDe(parte) {
  if (!parte) return '';
  var dado = parte.body && parte.body.data;
  if (parte.mimeType === 'text/plain' && dado) return decodificar(dado);
  var partes = parte.parts || [];
  for (var i = 0; i < partes.length; i++) {
    var t = textoDe(partes[i]);
    if (t) return t;
  }
  if (parte.mimeType === 'text/html' && dado) {
    return decodificar(dado).replace(/<br\s*\/?>|<\/p>|<\/tr>|<\/div>/gi, '\n').replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ').replace(/&iacute;/g, 'í').replace(/[ \t]+/g, ' ');
  }
  return '';
}

function decodificar(dado) {
  return Utilities.newBlob(Utilities.base64DecodeWebSafe(dado)).getDataAsString('UTF-8');
}

/** Rode uma vez no editor: pede a autorização e mostra quantos avisos de distribuição chegaram em 15 dias. */
function testarDistribuicoes() {
  Logger.log('avisos de distribuição nos últimos 15 dias: ' + distribuicoes({ dias: 15 }).mensagens.length);
}
