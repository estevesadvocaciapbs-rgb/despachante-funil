/**
 * Painel de Gestão — site (27/11/2026) — Esteves Advocacia.
 *
 * Projeto Apps Script PRÓPRIO ("Painel de Gestão - site"), separado da Ponte Planilha, publicado como App da Web:
 *   Executar como: "Eu" (conta do escritório)  |  Quem pode acessar: "Qualquer pessoa".
 * A porta é a SENHA DO PAINEL, que o próprio Dr. Lucas cadastra em Configurações do projeto > Propriedades do
 * script > SENHA_PAINEL (ninguém mais vê). O login do Google por pessoa não serve aqui: com duas contas no mesmo
 * Chrome o Google não abre o app. Errou 10 vezes, bloqueia 15 minutos. Trocar a senha desconecta todos os aparelhos.
 * A planilha continua sendo o banco de dados (montada pelo painel.gs, 7h e 20h15).
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

function sSenha() { return PropertiesService.getScriptProperties().getProperty('SENHA_PAINEL') || ''; }
function sFicha(senha) {  // o aparelho guarda só esta ficha, nunca a senha
  return Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,
    'painel-gestao|' + senha, Utilities.Charset.UTF_8));
}

/** Confere a senha digitada e devolve a ficha que o navegador guarda. */
function entrar(senha) {
  var cache = CacheService.getScriptCache(), tent = Number(cache.get('tentativas') || 0), certa = sSenha();
  if (!certa) return JSON.stringify({ erro: 'A senha do painel ainda não foi cadastrada no Google.' });
  if (tent >= 10) return JSON.stringify({ erro: 'Muitas tentativas erradas. Espere 15 minutos.' });
  if (String(senha) !== certa) {
    cache.put('tentativas', String(tent + 1), 900);
    Utilities.sleep(700);
    return JSON.stringify({ erro: 'Senha incorreta.' });
  }
  return JSON.stringify({ ficha: sFicha(certa) });
}

/** Tudo que a página precisa, numa chamada só (a página filtra e soma no navegador). */
function dados(ficha) {
  var certa = sSenha();
  if (!certa || ficha !== sFicha(certa)) return JSON.stringify({ sair: true });
  var pl = SpreadsheetApp.openById(SITE_PLANILHA);
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
    planilha: pl.getUrl()
  });
}
