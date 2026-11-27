/**
 * Painel de Gestão (27/11/2026) — Esteves Advocacia. Arquivo "painel.gs" do projeto "Ponte Planilha" (o mesmo
 * da ponte_planilha.gs), na conta do escritório. Sem IA: só lê nomes, datas e autores dos arquivos do Drive
 * (nunca o conteúdo) e monta a planilha "Painel de Gestão – produtividade e custos" (id em PAINEL_ID; vazio no
 * GitHub).
 *
 * Fontes:
 *  - Drive (aqui mesmo, nos servidores do Google): arquivos criados ou editados nas pastas dos clientes. Em arquivo
 *    do Google (Documentos, Planilhas, Apresentações) o histórico de versões dá quem editou e quando; as versões da
 *    mesma pessoa com menos de 15 min de intervalo formam uma sessão de trabalho (mínimo de 5 min por sessão).
 *    Em .docx, PDF e imagem o Drive só guarda criação e última alteração: conta como atividade, com 0 minuto.
 *  - EasyJur: o despachante (GitHub, painel_easyjur.py) manda os prazos da semana e os clientes com processo ativo
 *    pela ação "painel_easyjur" do doPost (ver ponte_planilha.gs); o EasyJur recusa o IP do VPS.
 *  - WhatsApp: a planilha "Conversas WhatsApp – banco diário" (PLANILHA_ID, da ponte_planilha.gs).
 *
 * O Google não registra o tempo em que um arquivo ficou só aberto, sem edição, em nenhuma conta; isso não entra.
 * Rodar uma vez no editor: painelConfigurar() (abas e gatilhos das 7h e 20h) e painelInicial() (últimos 30 dias).
 */
var PAINEL_ID = '';
var PAINEL_DIAS_DIARIO = 3;      // cada rodada refaz os 3 últimos dias (pega edição tardia sem duplicar)
var PAINEL_GAP_MIN = 15;         // pausa que fecha uma sessão de edição
var PAINEL_MIN_SESSAO = 5;       // minutos mínimos de uma sessão (uma versão só não tem duração no Drive)
var PAINEL_PARADO_DIAS = 7;
var PAINEL_RAIZES = {            // pasta-raiz -> como achar o cliente no caminho
  '12fAiFgU-TracmvfpMvoDGJ6QVqqMOiBw': 'processos',   // Processos › ÁREA › Cliente
  '1x8EkMbdFFHt8Bl4uF-QRHxi8t9jfbYH8': 'whatsapp',    // Mídias - Whatsapp › telefone (salvo pela Za.Ia)
  '1jqVqavdpzNcFqCORzqfJCX1LY7Nm7mGS': 'oc',          // OC PARAUAPEBAS DIRETO 2 › grupo › Cliente
  '1wZTPc2o0awmByhqYJQUp8MQ3b72O7NWN': 'escritorio'   // resto do Escritório (modelos, petições; sem cliente)
};
var PAINEL_FORA = ['Painel de Gestão'];   // pastas do Escritório que não são trabalho de cliente
var PAINEL_COLS = ['data', 'cliente', 'área', 'origem', 'pessoa', 'email', 'ação', 'início', 'fim', 'minutos',
  'custo (R$)', 'arquivo', 'tipo', 'caminho', 'link', 'id_arquivo', 'id_pasta_cliente', 'gravado em'];
var PAINEL_PECAS = [  // palavra no prazo -> expressão que o nome do arquivo (sem acento) deve ter
  ['replica', 'replica|manifesta.*contesta|contestacao e doc'], ['impugnacao', 'impugna'], ['contestacao', 'contesta'], ['contrarrazo', 'contrarraz'],
  ['contraminuta', 'contraminuta'], ['recurso ordinario', 'recurso'], ['recurso de revista', 'revista'],
  ['agravo', 'agravo'], ['embargos', 'embargo'], ['quesito', 'quesito'], ['calculo', 'calculo'],
  ['alegacoes finais', 'alegac'], ['razoes finais', 'razoes'], ['emenda', 'emenda'], ['apelacao', 'apela'],
  ['manifesta', 'manifesta'], ['peticao inicial', 'inicial'], ['inicial', 'inicial'], ['recurso', 'recurso']
];

// ------------------------------------------------------------------ utilidades

function pPlanilha() {
  var pl = SpreadsheetApp.openById(PAINEL_ID);
  if (pl.getSpreadsheetTimeZone() !== FUSO) pl.setSpreadsheetTimeZone(FUSO);  // nasceu no fuso do Pacífico: datas viravam o dia
  return pl;
}

function pAba(nome) {
  var pl = pPlanilha();
  return pl.getSheetByName(nome) || pl.insertSheet(nome);
}

function pNormal(s) {
  return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
}

var P_VAZIAS = { de: 1, da: 1, do: 1, dos: 1, das: 1, e: 1, ltda: 1, sa: 1, me: 1, epp: 1, eireli: 1, cia: 1 };

function pPalavras(s) {
  return pNormal(s).split(' ').filter(function (w) { return w.length > 1 && !P_VAZIAS[w]; });
}

function pDia(d) { return Utilities.formatDate(d, FUSO, 'yyyy-MM-dd'); }
function pHora(d) { return Utilities.formatDate(d, FUSO, 'HH:mm'); }
function pData(txt) {  // 'AAAA-MM-DD' -> Date à 00h de Belém (a planilha guarda como data, sem hora)
  var p = String(txt).slice(0, 10).split('-');
  return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2], 3));
}

function pTodas(params) {
  var lista = [], token;
  do {
    params.pageToken = token;
    var r = Drive.Files.list(params);
    lista = lista.concat(r.files || []);
    token = r.nextPageToken;
  } while (token);
  return lista;
}

function pEquipe() {
  var sh = pAba('Equipe'), mapa = {};
  if (sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, 3).getValues().forEach(function (l) {
      if (l[0]) mapa[String(l[0]).trim().toLowerCase()] = { nome: String(l[1] || l[0]), custo: Number(l[2]) || 0 };
    });
  }
  return mapa;
}

// ------------------------------------------------------------------ onde está o arquivo (cliente pelo caminho)

var P_PASTAS = {};

function pPasta(id) {
  if (!P_PASTAS[id]) {
    try {
      P_PASTAS[id] = Drive.Files.get(id, { fields: 'id,name,parents' });
    } catch (e) {
      P_PASTAS[id] = { id: id, name: '', parents: [] };  // pasta sem acesso: fora do painel
    }
  }
  return P_PASTAS[id];
}

/** {raiz, cliente, area, caminho, idCliente} ou null quando o arquivo não é das pastas varridas. */
function pOnde(paiId) {
  var cadeia = [], id = paiId, n = 0;
  while (id && n++ < 15) {
    if (PAINEL_RAIZES[id]) break;
    var f = pPasta(id);
    cadeia.unshift(f);
    id = (f.parents || [])[0];
  }
  var raiz = PAINEL_RAIZES[id];
  if (!raiz) return null;
  var nomes = cadeia.map(function (f) { return f.name; });
  var caminho = nomes.join(' › ');
  if (raiz === 'processos' && cadeia.length >= 2) {
    return { raiz: raiz, area: nomes[0], cliente: nomes[1], idCliente: cadeia[1].id, caminho: caminho };
  }
  if (raiz === 'oc' && cadeia.length >= 2 && /CLIENTES/i.test(nomes[0])) {
    return { raiz: raiz, area: 'OC ' + nomes[0], cliente: nomes[1], idCliente: cadeia[1].id, caminho: caminho };
  }
  if (raiz === 'whatsapp' && cadeia.length >= 1) {
    return { raiz: raiz, area: 'WhatsApp', cliente: nomes[0], idCliente: cadeia[0].id, caminho: caminho };
  }
  if (raiz === 'escritorio' && cadeia.length >= 1 && PAINEL_FORA.indexOf(nomes[0]) < 0) {
    return { raiz: raiz, area: nomes[0], cliente: '', idCliente: '', caminho: caminho };
  }
  return null;
}

// ------------------------------------------------------------------ atividades de um arquivo

function pSessoes(revs) {
  var porPessoa = {}, sessoes = [];
  revs.forEach(function (r) {
    var u = r.lastModifyingUser || {};
    var k = (u.emailAddress || u.displayName || '?').toLowerCase();
    (porPessoa[k] = porPessoa[k] || { u: u, horas: [] }).horas.push(new Date(r.modifiedTime));
  });
  Object.keys(porPessoa).forEach(function (k) {
    var h = porPessoa[k].horas.sort(function (a, b) { return a - b; }), ini = h[0], fim = h[0];
    for (var i = 1; i <= h.length; i++) {
      if (i < h.length && h[i] - fim <= PAINEL_GAP_MIN * 60000 && pDia(h[i]) === pDia(ini)) { fim = h[i]; continue; }
      sessoes.push({ u: porPessoa[k].u, ini: ini, fim: fim });
      if (i < h.length) { ini = h[i]; fim = h[i]; }
    }
  });
  return sessoes;
}

function pAtividades(f, desde, automatico) {
  var criado = new Date(f.createdTime), mod = new Date(f.modifiedTime), lista = [];
  var nativo = f.mimeType.indexOf('application/vnd.google-apps.') === 0;
  if (nativo && !automatico) {
    try {
      var revs = (Drive.Revisions.list(f.id, {
        fields: 'revisions(modifiedTime,lastModifyingUser(displayName,emailAddress))', pageSize: 1000
      }).revisions || []).filter(function (r) { return new Date(r.modifiedTime) >= desde; });
      pSessoes(revs).forEach(function (s) {
        var min = Math.max(Math.round((s.fim - s.ini) / 60000), PAINEL_MIN_SESSAO);
        var acao = (criado >= new Date(s.ini.getTime() - 60000) && criado <= s.fim) ? 'criou' : 'editou';
        lista.push({ u: s.u, quando: s.ini, fim: s.fim, minutos: min, acao: acao });
      });
      if (lista.length) return lista;
    } catch (e) { /* sem histórico: cai no caso simples */ }
  }
  var dono = (f.owners || [])[0] || {};
  if (criado >= desde) {
    lista.push({ u: (mod - criado < 10 * 60000) ? (f.lastModifyingUser || dono) : dono, quando: criado,
      fim: criado, minutos: 0, acao: 'criou' });
  }
  if (mod - criado >= 10 * 60000 && mod >= desde) {
    lista.push({ u: f.lastModifyingUser || {}, quando: mod, fim: mod, minutos: 0, acao: 'editou' });
  }
  return lista;
}

// ------------------------------------------------------------------ varredura

/** Refaz as linhas da aba Arquivos dos últimos `dias` dias (o que é mais antigo fica como está). */
function painelVarrer(dias) {
  dias = dias || PAINEL_DIAS_DIARIO;
  var t0 = Date.now();
  var desde = pData(pDia(new Date(Date.now() - (dias - 1) * 864e5)));
  var equipe = pEquipe(), escritorio = Session.getEffectiveUser().getEmail().toLowerCase();
  var arquivos = pTodas({
    q: "modifiedTime > '" + desde.toISOString() + "' and trashed = false and " +
      "mimeType != 'application/vnd.google-apps.folder'",
    fields: 'nextPageToken,files(id,name,mimeType,createdTime,modifiedTime,parents,webViewLink,' +
      'owners(displayName,emailAddress),lastModifyingUser(displayName,emailAddress))',
    pageSize: 1000
  });
  var gravado = Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd HH:mm'), novas = [];
  arquivos.forEach(function (f) {
    if (Date.now() - t0 > 300000) throw new Error('varredura passou de 5 min; rode com menos dias');
    if (f.id === PAINEL_ID || f.id === PLANILHA_ID || !(f.parents || []).length) return;
    var onde = pOnde(f.parents[0]);
    if (!onde) return;
    var automatico = onde.raiz === 'whatsapp' || /^Conversa - /.test(f.name);
    pAtividades(f, desde, automatico).forEach(function (a) {
      var email = String((a.u || {}).emailAddress || '').toLowerCase();
      var origem = automatico ? 'automático (WhatsApp)'
        : (email === escritorio || equipe[email]) ? 'equipe' : 'cliente/terceiro';
      var pessoa = equipe[email] ? equipe[email].nome
        : email === escritorio ? 'conta do escritório' : ((a.u || {}).displayName || email || '?');
      novas.push([pData(pDia(a.quando)), onde.cliente, onde.area, origem, pessoa, email, a.acao, pHora(a.quando),
        pHora(a.fim), a.minutos, '', f.name, f.mimeType.split('/').pop().replace('vnd.google-apps.', 'google '),
        onde.caminho, f.webViewLink || '', f.id, onde.idCliente, gravado]);
    });
  });
  var sh = pAba('Arquivos'), largura = PAINEL_COLS.length;
  var atuais = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, largura).getValues() : [];
  var corte = pDia(desde);
  var todas = atuais.filter(function (l) { return l[0] !== '' && dataTexto(l[0]) < corte; }).concat(novas);
  todas.sort(function (a, b) {
    var x = dataTexto(a[0]) + a[7], y = dataTexto(b[0]) + b[7];
    return x < y ? 1 : x > y ? -1 : 0;   // mais novo em cima
  });
  todas.forEach(function (l, i) {  // custo ao vivo: muda sozinho quando o custo da hora é trocado na aba Equipe
    var r = i + 2;
    if (l[9] === '' || l[9] === null) l[9] = 0;  // coluna só de números: com vazio o QUERY não soma
    l[10] = '=IF(J' + r + '="";0;J' + r + '/60*IFERROR(VLOOKUP(F' + r + ';Equipe!A:C;3;FALSE);0))';
  });
  sh.clearContents();
  sh.getRange(1, 1, 1, largura).setValues([PAINEL_COLS]).setFontWeight('bold');
  sh.setFrozenRows(1);
  if (todas.length) {
    sh.getRange(2, 1, todas.length, 1).setNumberFormat('dd/MM/yyyy');
    sh.getRange(2, 8, todas.length, 2).setNumberFormat('@');
    sh.getRange(2, 16, todas.length, 2).setNumberFormat('@');
    sh.getRange(2, 1, todas.length, largura).setValues(todas);
    sh.getRange(2, 11, todas.length, 1).setNumberFormat('R$ #,##0.00');
  }
  Logger.log('Arquivos: ' + novas.length + ' atividade(s) desde ' + corte + ' em ' + arquivos.length +
    ' arquivo(s) alterado(s); total na aba ' + todas.length);
  return novas.length;
}

// ------------------------------------------------------------------ cadastro de clientes (pastas) e EasyJur

function pPastasClientes() {
  var lista = [];
  Object.keys(PAINEL_RAIZES).forEach(function (raizId) {
    var raiz = PAINEL_RAIZES[raizId];
    if (raiz !== 'processos' && raiz !== 'oc') return;
    pTodas({ q: "'" + raizId + "' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
      fields: 'nextPageToken,files(id,name)', pageSize: 1000 }).forEach(function (area) {
      if (raiz === 'oc' && !/CLIENTES/i.test(area.name)) return;  // fichas e kits não são clientes
      pTodas({ q: "'" + area.id + "' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields: 'nextPageToken,files(id,name,webViewLink)', pageSize: 1000 }).forEach(function (c) {
        lista.push({ id: c.id, nome: c.name, area: (raiz === 'oc' ? 'OC ' : '') + area.name, link: c.webViewLink });
      });
    });
  });
  return lista;
}

/** Partes do nome da pasta ('Alexander x ENGEMON RJ' -> [[alexander], [engemon, rj]]), sem sufixo '- FERNANDA'. */
function pPartes(nomePasta) {
  return pNormal(String(nomePasta).replace(/\s+-\s+.*$/, '')).split(/ x /).map(pPalavras)
    .filter(function (p) { return p.length; });
}

/** Melhor pasta para um texto (nome do cliente ou descrição do prazo): todas as palavras de uma parte do nome
 * da pasta precisam estar no texto; ganha a parte com mais palavras (empate: a 1ª). Parte de uma palavra só vale
 * se a palavra tiver 6 letras ou mais ('Alexander' sim, 'Maria' não). */
function pAcharPasta(texto, pastas) {
  var alvo = {}, melhor = null, nota = 0;
  pPalavras(texto).forEach(function (w) { alvo[w] = 1; });
  pastas.forEach(function (p) {
    p.partes.forEach(function (parte) {
      var n = parte.length;
      if (n === 1 && parte[0].length < 6) return;
      if (n > nota && parte.every(function (w) { return alvo[w]; })) { melhor = p; nota = n; }
    });
  });
  return melhor;
}

function pAjustes() {
  var sh = pAba('Ajustes de pasta'), mapa = {};
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, 3).setValues([['nome no EasyJur (como aparece no prazo)', 'link ou id da pasta do cliente',
      'observação']]).setFontWeight('bold');
  }
  if (sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, 2).getValues().forEach(function (l) {
      var m = String(l[1]).match(/[-\w]{25,}/);
      if (l[0] && m) mapa[pNormal(l[0])] = m[0];
    });
  }
  return mapa;
}

function pLerTabela(nome) {
  var sh = pPlanilha().getSheetByName(nome);
  if (!sh || sh.getLastRow() < 2) return [];
  var v = sh.getDataRange().getValues(), cab = v.shift();
  return v.map(function (l) { var o = {}; cab.forEach(function (c, i) { o[c] = l[i]; }); return o; });
}

/** Ação "painel_easyjur" do doPost: o despachante manda prazos e clientes ativos; fica em abas ocultas. */
function painelGravarEasyjur(prazos, clientes) {
  [['_prazos_easyjur', prazos], ['_clientes_easyjur', clientes]].forEach(function (par) {
    var linhas = par[1] || [];
    if (!linhas.length) return;
    var cab = Object.keys(linhas[0]), sh = pAba(par[0]);
    sh.clearContents();
    sh.getRange(1, 1, 1, cab.length).setValues([cab]);
    sh.getRange(2, 1, linhas.length, cab.length).setNumberFormat('@')
      .setValues(linhas.map(function (o) { return cab.map(function (c) { return o[c] == null ? '' : String(o[c]); }); }));
    sh.hideSheet();
  });
  var p = PropertiesService.getScriptProperties();
  p.setProperty('PAINEL_EASYJUR_EM', Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd HH:mm'));
  return { ok: true, prazos: (prazos || []).length, clientes: (clientes || []).length };
}

// ------------------------------------------------------------------ abas montadas pelo script

function pEscrever(nome, cab, linhas, formatos) {
  var sh = pAba(nome);
  sh.clearContents();
  sh.getRange(1, 1, 1, cab.length).setValues([cab]).setFontWeight('bold');
  sh.setFrozenRows(1);
  if (linhas.length) {
    (formatos || []).forEach(function (fm) { sh.getRange(2, fm[0], linhas.length, 1).setNumberFormat(fm[1]); });
    sh.getRange(2, 1, linhas.length, cab.length).setValues(linhas);
  }
  return sh;
}

function painelMontar() {
  var hoje = pData(pDia(new Date())), pastas = pPastasClientes();
  pastas.forEach(function (p) { p.partes = pPartes(p.nome); });
  var porId = {};
  pastas.forEach(function (p) { porId[p.id] = p; });
  var ajustes = pAjustes();
  var arqs = pLerTabela('Arquivos');

  // último trabalho da equipe por pasta
  var ultimo = {}, conta30 = {};
  arqs.forEach(function (a) {
    if (a['origem'] !== 'equipe' || !a['id_pasta_cliente']) return;
    var k = String(a['id_pasta_cliente']), d = new Date(a['data']);
    if (!ultimo[k] || d > ultimo[k]) ultimo[k] = d;
    if (hoje - d <= 30 * 864e5) conta30[k] = (conta30[k] || 0) + 1;
  });

  // clientes com processo ativo no EasyJur -> pasta
  var ativos = {};  // id da pasta -> {id_pessoa, processos}
  pLerTabela('_clientes_easyjur').forEach(function (c) {
    var aj = ajustes[pNormal(c['nome'])];
    var p = aj ? porId[aj] : pAcharPasta(c['nome'], pastas);
    if (p) ativos[p.id] = { id_pessoa: c['id_pessoa'], processos: Number(c['processos']) || 0 };
  });

  // última conversa no WhatsApp por cliente (id da pessoa no EasyJur)
  var conversa = {};
  try {
    var conv = SpreadsheetApp.openById(PLANILHA_ID).getSheetByName('Conversas').getDataRange().getValues();
    conv.shift();
    conv.forEach(function (l) {
      var pid = String(l[6] || ''), d = new Date(l[0]);
      if (pid && (!conversa[pid] || d > conversa[pid])) conversa[pid] = d;
    });
    pEscrever('Conversas (WhatsApp)', ['data', 'nome', 'telefone', 'tipo', 'id_pessoa_easyjur', 'total msgs',
      'sem resposta', 'quem respondeu', '1ª msg', 'última msg'],
      conv.filter(function (l) { return hoje - new Date(l[0]) <= 60 * 864e5; })
        .map(function (l) { return [l[0], l[3], String(l[4]), l[5], String(l[6] || ''), l[11], l[16], l[18], l[13], l[14]]; }),
      [[1, 'dd/MM/yyyy'], [3, '@'], [5, '@']]);
  } catch (e) { Logger.log('planilha das conversas não lida: ' + e); }

  // Clientes parados: com processo ativo ou com trabalho registrado, sem trabalho da equipe há mais de 7 dias
  var inicio = arqs.length ? arqs.reduce(function (m, a) { var d = new Date(a['data']); return d < m ? d : m; },
    new Date()) : hoje;
  var parados = [];
  pastas.forEach(function (p) {
    var u = ultimo[p.id], at = ativos[p.id];
    if (!at && !u) return;
    var dias = u ? Math.round((hoje - pData(pDia(u))) / 864e5) : null;
    if (dias !== null && dias <= PAINEL_PARADO_DIAS) return;
    var c = at && conversa[String(at.id_pessoa)];
    parados.push([p.nome, p.area, u || 'antes de ' + Utilities.formatDate(inicio, FUSO, 'dd/MM/yyyy'),
      dias === null ? '' : dias, at ? at.processos : 0, c || '', p.link]);
  });
  parados.sort(function (a, b) { return (b[3] === '' ? 9999 : b[3]) - (a[3] === '' ? 9999 : a[3]); });
  pEscrever('Clientes parados', ['cliente (pasta)', 'área', 'último trabalho da equipe', 'dias parado',
    'processos ativos', 'última conversa WhatsApp', 'pasta'], parados, [[6, 'dd/MM/yyyy']]);

  // Prazos da semana x documento novo na pasta
  var linhas = [];
  pLerTabela('_prazos_easyjur').forEach(function (pz) {
    var nome = pz['nome_cliente'], desc = String(pz['descricao'] || '').replace(/\s+/g, ' ').trim();
    var aj = ajustes[pNormal(nome)];
    var pasta = aj ? porId[aj] : (pAcharPasta(nome, pastas) || pAcharPasta(desc, pastas));
    var texto = pNormal(desc), peca = null;
    for (var i = 0; i < PAINEL_PECAS.length; i++) if (texto.indexOf(PAINEL_PECAS[i][0]) >= 0) { peca = PAINEL_PECAS[i]; break; }
    var desde = pz['data_cadastro'] ? pData(pz['data_cadastro']) : new Date(hoje - 15 * 864e5);
    var novos = [], comPeca = [];
    if (pasta) {
      novos = pArquivosDesde(pasta.id, desde);
      comPeca = peca ? novos.filter(function (n) { return new RegExp(peca[1]).test(pNormal(n)); }) : [];
    }
    var alerta;
    if (pz['status'] === 'C') alerta = '✔ concluído';
    else if (pz['status'] === 'S') alerta = 'cancelado';
    else if (!pasta) alerta = '⚠ pasta do cliente não encontrada';
    else if (peca && !comPeca.length) alerta = '🔴 sem documento de ' + peca[0];
    else if (!novos.length) alerta = '🔴 sem documento novo';
    else alerta = '🟢 tem documento novo';
    linhas.push([pData(pz['data']), pz['status'], pz['advogado'], nome || '(sem cliente no EasyJur)', desc.slice(0, 160),
      peca ? peca[0] : '', pasta ? pasta.nome : '', novos.length, (comPeca.length ? comPeca : novos).slice(0, 3).join(' | '),
      alerta, pasta ? pasta.link : '']);
  });
  linhas.sort(function (a, b) { return a[0] - b[0]; });
  pEscrever('Prazos da semana', ['prazo', 'status', 'advogado', 'cliente (EasyJur)', 'descrição', 'peça',
    'pasta encontrada', 'arquivos novos desde o lançamento', 'exemplos', 'alerta', 'pasta'], linhas, [[1, 'dd/MM/yyyy']]);

  pResumos();
  PropertiesService.getScriptProperties().setProperty('PAINEL_MONTADO_EM',
    Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd HH:mm'));
  Logger.log('Painel: ' + pastas.length + ' pasta(s) de cliente, ' + Object.keys(ativos).length +
    ' com processo ativo achada(s), ' + parados.length + ' parado(s), ' + linhas.length + ' prazo(s)');
}

/** Nomes dos arquivos criados ou alterados desde `desde` na pasta do cliente e subpastas (até 4 níveis). */
function pArquivosDesde(pastaId, desde) {
  var nomes = [], fila = [[pastaId, 0]];
  while (fila.length) {
    var it = fila.shift();
    pTodas({ q: "'" + it[0] + "' in parents and trashed = false", fields: 'nextPageToken,files(id,name,mimeType,createdTime,modifiedTime)',
      pageSize: 1000 }).forEach(function (f) {
      if (f.mimeType === 'application/vnd.google-apps.folder') { if (it[1] < 4) fila.push([f.id, it[1] + 1]); return; }
      if (new Date(f.modifiedTime) >= desde || new Date(f.createdTime) >= desde) nomes.push(f.name);
    });
  }
  return nomes;
}

/** Abas só de fórmulas (recalculam sozinhas, inclusive quando o custo da hora muda). */
function pResumos() {
  var ult30 = '"&TEXT(TODAY()-30;"yyyy-mm-dd")&"';
  var sh = pAba('Atividades por cliente');
  sh.clearContents();
  sh.getRange('A1').setValue('Últimos 30 dias, trabalho da equipe (origem = equipe)').setFontWeight('bold');
  sh.getRange('A2').setFormula('=IFERROR(QUERY(Arquivos!A:R;"select B, C, count(L), sum(J), sum(K), max(A) ' +
    'where D = \'equipe\' and B <> \'\' and A >= date \'' + ult30 + '\' group by B, C order by count(L) desc ' +
    'label B \'cliente\', C \'área\', count(L) \'atividades\', sum(J) \'minutos\', sum(K) \'custo (R$)\', ' +
    'max(A) \'última\' format max(A) \'dd/mm/yyyy\'";1);"sem dados ainda")');
  sh.getRange('I1').setValue('Hoje').setFontWeight('bold');
  sh.getRange('I2').setFormula('=IFERROR(QUERY(Arquivos!A:R;"select B, count(L), sum(J) where D = \'equipe\' ' +
    'and A = date \'"&TEXT(TODAY();"yyyy-mm-dd")&"\' group by B order by count(L) desc label B \'cliente\', ' +
    'count(L) \'atividades\', sum(J) \'minutos\'";1);"nada hoje ainda")');

  sh = pAba('Por pessoa e dia');
  sh.clearContents();
  sh.getRange('A1').setValue('Cada pessoa em cada dia (a lista dos arquivos está na aba Arquivos)').setFontWeight('bold');
  sh.getRange('A2').setFormula('=IFERROR(QUERY(Arquivos!A:R;"select A, E, count(L), sum(J), sum(K) ' +
    'where D = \'equipe\' group by A, E order by A desc label A \'dia\', E \'pessoa\', count(L) \'arquivos\', ' +
    'sum(J) \'minutos\', sum(K) \'custo (R$)\'";1);"sem dados ainda")');
  sh.getRange('A:A').setNumberFormat('dd/MM/yyyy');

  sh = pAba('Custo por cliente');
  sh.clearContents();
  sh.getRange('A1').setValue('Custo por cliente e por mês (horas x custo da hora da aba Equipe)').setFontWeight('bold');
  sh.getRange('A2').setFormula('=IFERROR(QUERY(Arquivos!A:R;"select B, year(A), month(A)+1, sum(J), sum(K), count(L) ' +
    'where D = \'equipe\' and B <> \'\' group by B, year(A), month(A)+1 order by year(A) desc, month(A)+1 desc, ' +
    'sum(K) desc label B \'cliente\', year(A) \'ano\', month(A)+1 \'mês\', sum(J) \'minutos\', sum(K) \'custo (R$)\', ' +
    'count(L) \'atividades\'";1);"sem dados ainda")');
  sh.getRange('I1').setValue('Custo por tipo de atividade (arquivo), 30 dias').setFontWeight('bold');
  sh.getRange('I2').setFormula('=IFERROR(QUERY(Arquivos!A:R;"select B, L, sum(J), sum(K) where D = \'equipe\' ' +
    'and J > 0 and A >= date \'' + ult30 + '\' group by B, L order by sum(K) desc label B \'cliente\', ' +
    'L \'arquivo\', sum(J) \'minutos\', sum(K) \'custo (R$)\'";1);"sem dados ainda")');

  sh = pAba('Visão do cliente');
  sh.getRange('A1').setValue('Digite parte do nome do cliente →').setFontWeight('bold');
  if (!sh.getRange('B1').getValue()) sh.getRange('B1').setValue('Alexander');
  sh.getRange('A3').setValue('Arquivos').setFontWeight('bold');
  sh.getRange('A4').setFormula('=IFERROR(FILTER({Arquivos!A2:A\\Arquivos!E2:E\\Arquivos!G2:G\\Arquivos!J2:J\\' +
    'Arquivos!K2:K\\Arquivos!L2:L};ISNUMBER(SEARCH($B$1;Arquivos!B2:B)));"nada")');
  sh.getRange('H3').setValue('Prazos').setFontWeight('bold');
  sh.getRange('H4').setFormula('=IFERROR(FILTER({\'Prazos da semana\'!A2:A\\\'Prazos da semana\'!F2:F\\' +
    '\'Prazos da semana\'!J2:J};ISNUMBER(SEARCH($B$1;\'Prazos da semana\'!D2:D&\'Prazos da semana\'!G2:G)));"nada")');
  sh.getRange('L3').setValue('WhatsApp (60 dias)').setFontWeight('bold');
  sh.getRange('L4').setFormula('=IFERROR(FILTER({\'Conversas (WhatsApp)\'!A2:A\\\'Conversas (WhatsApp)\'!F2:F\\' +
    '\'Conversas (WhatsApp)\'!G2:G\\\'Conversas (WhatsApp)\'!H2:H};ISNUMBER(SEARCH($B$1;' +
    '\'Conversas (WhatsApp)\'!B2:B)));"nada")');
  sh.getRange('M:M').setNumberFormat('0');
  sh.getRange('A:A').setNumberFormat('dd/MM/yyyy');
  sh.getRange('H:H').setNumberFormat('dd/MM/yyyy');
  sh.getRange('L:L').setNumberFormat('dd/MM/yyyy');
}

// ------------------------------------------------------------------ instalação e rodadas

function painelDiario() {
  painelVarrer(PAINEL_DIAS_DIARIO);
  painelMontar();
}

/** Rode uma vez: os 30 últimos dias (se passar de 5 min, rode painelVarrer(15) e depois painelMontar()). */
function painelInicial() {
  painelVarrer(30);
  painelMontar();
}

/** Rode uma vez no editor: cria as abas fixas e os gatilhos das 7h e das 20h. */
function painelConfigurar() {
  var eq = pAba('Equipe');
  if (eq.getLastRow() === 0) {
    eq.getRange(1, 1, 1, 4).setValues([['email (login do Google)', 'nome', 'custo da hora (R$)', 'função']])
      .setFontWeight('bold');
    eq.getRange(2, 1, 1, 4).setValues([[Session.getEffectiveUser().getEmail(), 'conta do escritório (login comum)',
      '', 'enquanto a equipe usa o mesmo login']]);
  }
  var como = pAba('Como ler');
  como.clearContents();
  como.getRange(1, 1, 9, 1).setValues([
    ['Painel de Gestão: atualizado sozinho às 7h e às 20h (sem IA).'],
    ['Arquivos: cada arquivo criado ou editado nas pastas dos clientes, com quem fez, quando e quanto tempo.'],
    ['Tempo só existe em arquivo do Google (Documentos, Planilhas): sessões de edição, mínimo de 5 min cada.'],
    ['Word, PDF e imagem contam como atividade com 0 minuto. Tempo só aberto, sem editar, o Google não registra.'],
    ['Quem fez = login do Google que salvou. Enquanto todos usam a conta do escritório, aparece "conta do escritório".'],
    ['Origem: equipe (trabalho do escritório), automático (WhatsApp salvo pela Za.Ia) ou cliente/terceiro.'],
    ['Custo = minutos ÷ 60 × custo da hora da pessoa na aba Equipe (muda na hora em que o valor é trocado).'],
    ['Prazos da semana vêm do EasyJur; o alerta diz se a pasta do cliente tem documento novo para o prazo.'],
    ['Pasta errada ou não achada num prazo: escreva o nome do cliente e o link da pasta na aba Ajustes de pasta.']
  ]);
  pAjustes();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'painelDiario') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('painelDiario').timeBased().everyDays(1).atHour(7).nearMinute(0).inTimezone(FUSO).create();
  ScriptApp.newTrigger('painelDiario').timeBased().everyDays(1).atHour(20).nearMinute(15).inTimezone(FUSO).create();
  var pl = pPlanilha(), s1 = pl.getSheetByName('Página1') || pl.getSheetByName('Sheet1');
  if (s1 && pl.getSheets().length > 1) pl.deleteSheet(s1);
  Logger.log('Painel configurado: abas criadas e gatilhos das 7h e 20h. Agora rode painelInicial.');
}
