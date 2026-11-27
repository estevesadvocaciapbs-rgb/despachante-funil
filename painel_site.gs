/**
 * Painel de Gestão — site (27/11/2026) — Esteves Advocacia.
 *
 * Projeto Apps Script PRÓPRIO ("Painel de Gestão - site"), separado da Ponte Planilha, publicado como App da Web:
 *   Executar como: "Usuário que acessa o app"  |  Quem pode acessar: "Qualquer pessoa com Conta do Google".
 * Assim só abre os dados quem tem acesso à planilha do painel (o Google confere o login de cada um); quem não tem
 * vê a tela de "sem acesso". A planilha continua sendo o banco de dados (montada pelo painel.gs, 7h e 20h15).
 *
 * Arquivos no editor: Código.gs (este) e index.html (painel_site.html no GitHub).
 * Repositório PÚBLICO: aqui só o código; o id da planilha fica vazio no GitHub e é colado no editor.
 */
var SITE_PLANILHA = '';   // id da planilha "Painel de Gestão – produtividade e custos"
var SITE_FUSO = 'America/Belem';
var SITE_DIAS = 120;      // até quantos dias de arquivos o site carrega

function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('Painel de Gestão · Esteves Advocacia')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function sTexto(v, fmt) {
  if (v instanceof Date) return Utilities.formatDate(v, SITE_FUSO, fmt || 'yyyy-MM-dd');
  return v === null || v === undefined ? '' : v;
}

function sAba(pl, nome) {
  var sh = pl.getSheetByName(nome);
  if (!sh || sh.getLastRow() < 2) return [];
  var v = sh.getDataRange().getValues();
  v.shift();
  return v;
}

/** Tudo que a página precisa, numa chamada só (a página filtra e soma no navegador). */
function dados() {
  var pl;
  try { pl = SpreadsheetApp.openById(SITE_PLANILHA); }
  catch (e) { return JSON.stringify({ semAcesso: true, usuario: Session.getActiveUser().getEmail() }); }
  var corte = Utilities.formatDate(new Date(Date.now() - SITE_DIAS * 864e5), SITE_FUSO, 'yyyy-MM-dd');
  var gravado = '';
  // Arquivos: data, cliente, área, origem, pessoa, ação, início, fim, minutos, custo, arquivo, tipo, link
  var arquivos = sAba(pl, 'Arquivos').filter(function (l) { return sTexto(l[0]) >= corte; }).map(function (l) {
    var g = String(sTexto(l[17], 'yyyy-MM-dd HH:mm'));
    if (g > gravado) gravado = g;
    return [sTexto(l[0]), l[1], l[2], l[3], l[4], l[6], String(sTexto(l[7], 'HH:mm')), String(sTexto(l[8], 'HH:mm')),
      Number(l[9]) || 0, Number(l[10]) || 0, l[11], l[12], l[14]];
  });
  // Prazos: prazo, status, advogado, cliente, descrição, peça, pasta achada, nº arquivos novos, exemplos, alerta, pasta
  var prazos = sAba(pl, 'Prazos da semana').map(function (l) {
    return [sTexto(l[0]), l[1], l[2], l[3], l[4], l[5], l[6], l[7], l[8], l[9], l[10]];
  });
  // Parados: cliente, área, último trabalho, dias, processos ativos, última conversa, pasta
  var parados = sAba(pl, 'Clientes parados').map(function (l) {
    return [l[0], l[1], String(sTexto(l[2])), l[3], l[4], sTexto(l[5]), l[6]];
  });
  // Conversas: data, nome, tipo, total msgs, sem resposta, quem respondeu, 1ª msg, última msg (telefone fica de fora)
  var conversas = sAba(pl, 'Conversas (WhatsApp)').map(function (l) {
    return [sTexto(l[0]), l[1], l[3], Number(l[5]) || 0, l[6], l[7], String(sTexto(l[8], 'HH:mm')),
      String(sTexto(l[9], 'HH:mm'))];
  });
  var equipe = sAba(pl, 'Equipe').map(function (l) { return [l[1], Number(l[2]) || 0, l[3]]; });
  return JSON.stringify({
    arquivos: arquivos, prazos: prazos, parados: parados, conversas: conversas, equipe: equipe,
    clientesAtivos: sAba(pl, '_clientes_easyjur').length, atualizado: gravado,
    planilha: pl.getUrl(), usuario: Session.getActiveUser().getEmail()
  });
}
