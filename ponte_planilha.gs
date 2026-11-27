/**
 * Ponte Planilha - conversas do dia (27/11/2026) — Esteves Advocacia.
 *
 * Projeto do Apps Script na conta do escritório que grava na planilha "Conversas WhatsApp – banco diário"
 * (id em PLANILHA_ID; na cópia do GitHub fica vazio). Projeto separado, e não ligado à planilha, porque o
 * Google não abre o editor ligado à planilha quando há duas contas no Chrome. Só abre a planilha do PLANILHA_ID.
 * Publicado como App da Web: executar como eu, acesso "qualquer pessoa"; sem a chave certa ele não faz nada.
 *
 * O despachante (conversas_dia.py) manda, todo dia às 19h, uma linha por conversa do WhatsApp com SÓ números e
 * horários (nunca o texto das mensagens). A gravação é por dia: regravar um dia troca as linhas dele, sem duplicar.
 *
 * Segurança: a chave fica nas Propriedades do script (função configurar), nunca no código.
 */
var PLANILHA_ID = '';
var ABA_DADOS = 'Conversas';
var ABA_CLIENTES = '_clientes';
var ABA_RESUMO = 'Resumo';
var FUSO = 'America/Belem';

/** Rode UMA vez no editor: cria as abas, pede a autorização e mostra a chave (GOOGLE_PLANILHA_CHAVE). */
function configurar() {
  var props = PropertiesService.getScriptProperties();
  var chave = props.getProperty('CHAVE');
  if (!chave) {
    chave = Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, '');
    props.setProperty('CHAVE', chave);
  }
  aba(ABA_DADOS);
  aba(ABA_CLIENTES).hideSheet();
  montarResumo();
  aba(ABA_RESUMO).getRange('A:A').setNumberFormat('dd/MM/yyyy');
  aba(ABA_RESUMO).getRange('I:I').setNumberFormat('dd/MM/yyyy');
  Logger.log('Pronto. As abas foram criadas e a chave foi gerada. Para ver a chave, rode a função mostrarChave.');
}

/** Mostra a chave (GOOGLE_PLANILHA_CHAVE) no registro de execução, para copiar. */
function mostrarChave() {
  Logger.log(PropertiesService.getScriptProperties().getProperty('CHAVE'));
}

function doPost(e) {
  try {
    var p = JSON.parse(e.postData.contents);
    var chave = PropertiesService.getScriptProperties().getProperty('CHAVE');
    if (!chave || p.chave !== chave) return saida({ ok: false, erro: 'chave inválida' });
    var trava = LockService.getScriptLock();
    trava.waitLock(30000);
    try {
      if (p.acao === 'gravar_dia') return saida(gravarDias(p.colunas, p.dias, p.linhas));
      if (p.acao === 'ler_clientes') return saida(lerClientes());
      if (p.acao === 'gravar_clientes') return saida(gravarClientes(p.clientes));
      if (p.acao === 'teste') return saida(teste());
      if (p.acao === 'painel_easyjur') return saida(painelGravarEasyjur(p.prazos, p.clientes));  // painel.gs
      return saida({ ok: false, erro: 'ação desconhecida' });
    } finally {
      trava.releaseLock();
    }
  } catch (err) {
    return saida({ ok: false, erro: String(err).slice(0, 300) });
  }
}

function saida(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function aba(nome) {
  var pl = SpreadsheetApp.openById(PLANILHA_ID);
  return pl.getSheetByName(nome) || pl.insertSheet(nome);
}

function dataTexto(v) {
  return v instanceof Date ? Utilities.formatDate(v, FUSO, 'yyyy-MM-dd') : String(v);
}

/** Troca as linhas dos dias informados pelas novas (a 1ª coluna é sempre a data AAAA-MM-DD). */
function gravarDias(colunas, dias, linhas) {
  var sh = aba(ABA_DADOS);
  var largura = colunas.length;
  var atuais = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, largura).getValues() : [];
  var trocar = {};
  dias.forEach(function (d) { trocar[d] = true; });
  var ficam = atuais.filter(function (l) { return !trocar[dataTexto(l[0])]; });
  var todas = ficam.concat(linhas).sort(function (a, b) {
    var x = dataTexto(a[0]) + String(a[13]), y = dataTexto(b[0]) + String(b[13]);
    return x < y ? -1 : x > y ? 1 : 0;
  });
  sh.clearContents();
  sh.getRange(1, 1, 1, largura).setValues([colunas]).setFontWeight('bold');
  sh.setFrozenRows(1);
  if (todas.length) {
    // ids e telefone como texto (o telefone viraria número e perderia o formato)
    [2, 3, 5, 7].forEach(function (c) { sh.getRange(2, c, todas.length, 1).setNumberFormat('@'); });
    sh.getRange(2, 1, todas.length, largura).setValues(todas);
  }
  return { ok: true, linhas: linhas.length, total: todas.length };
}

/** Cache id da pessoa no EasyJur -> telefone (vazio = cadastro sem celular), para poupar a cota do EasyJur. */
function lerClientes() {
  var sh = aba(ABA_CLIENTES);
  var mapa = {};
  if (sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues().forEach(function (l) {
      if (l[0] !== '') mapa[String(l[0])] = String(l[1] || '');
    });
  }
  return { ok: true, clientes: mapa };
}

function gravarClientes(novos) {
  var mapa = lerClientes().clientes;
  Object.keys(novos || {}).forEach(function (k) { mapa[k] = String(novos[k] || ''); });
  var sh = aba(ABA_CLIENTES);
  var linhas = Object.keys(mapa).map(function (k) { return [k, mapa[k]]; });
  sh.clearContents();
  sh.getRange(1, 1, 1, 2).setValues([['id_pessoa_easyjur', 'telefone']]);
  if (linhas.length) {
    sh.getRange(2, 1, linhas.length, 2).setNumberFormat('@').setValues(linhas);
  }
  return { ok: true, total: linhas.length };
}

/** Aba Resumo: só fórmulas, recalculadas pelo próprio Google a cada gravação. A planilha está em português,
 * então o separador das fórmulas é ponto e vírgula (com vírgula dá "Erro de análise de fórmula"). */
function montarResumo() {
  var sh = aba(ABA_RESUMO);
  sh.clearContents();
  sh.getRange('A1').setValue('Por dia').setFontWeight('bold');
  sh.getRange('A2').setFormula(
    '=IFERROR(QUERY(Conversas!A:Z;"select A, count(B), sum(L), sum(Q), sum(I), sum(J), sum(K) where A is not null ' +
    'group by A order by A desc label count(B) \'conversas\', sum(L) \'mensagens\', sum(Q) \'sem resposta\', ' +
    'sum(I) \'msgs clientes\', sum(J) \'msgs equipe\', sum(K) \'msgs Annie\'";1);"sem dados ainda")');
  sh.getRange('I1').setValue('Conversas por tipo').setFontWeight('bold');
  sh.getRange('I2').setFormula(
    '=IFERROR(QUERY(Conversas!A:Z;"select A, count(B) where A is not null group by A pivot F order by A desc";1);"")');
}

/** Grava uma linha fictícia num dia de 1900 e apaga em seguida: confere que a ponte escreve. */
function teste() {
  var col = ['data', 'id_conversa'];
  var sh = aba(ABA_DADOS);
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, 2).setValues([col]);
    sh.appendRow(['1900-01-01', 'teste']);
    sh.deleteRow(2);
    return { ok: true };
  }
  var linha = sh.getLastRow() + 1;
  sh.getRange(linha, 1, 1, 2).setValues([['1900-01-01', 'teste']]);
  sh.deleteRow(linha);
  return { ok: true };
}
