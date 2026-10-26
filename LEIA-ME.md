# Despachante do funil — Esteves Advocacia

Programa pequeno, **sem IA**, que fica de plantão no GitHub **24 horas por dia,
todos os dias** (sábado, domingo e madrugada inclusive) e confere a Za.Ia **a cada 60 segundos**. Quando um lead triado aparece (tarefa ou
resumo no grupo), ele confere a agenda do advogado no EasyJur e manda ao lead
2 horários livres — o mais próximo de manhã e o mais próximo à tarde. Quando o
lead escolhe, grava a reunião no EasyJur e avisa o grupo só para conhecimento.
Não gasta tokens.

Casos que pedem julgamento (atendimento incompleto, criminal urgente, filtro de
viabilidade trabalhista, lead já atendido por alguém da equipe) ficam com as
rotinas do Claude, como hoje.

## Como colocar no ar (feito uma vez, por você)

1. Entre em https://github.com com a conta do escritório e crie um repositório
   novo chamado `despachante-funil`.
2. Envie para ele os arquivos desta pasta (`despachante.py`, `teste_regras.py`,
   `LEIA-ME.md` e a pasta `.github`). O Claude pode fazer este envio se você autorizar.
3. No repositório: **Settings › Secrets and variables › Actions › New repository secret**.
   Crie dois segredos (cole os valores direto ali, nunca no chat):
   - `ZAIA_TOKEN` — token novo gerado na Za.Ia (Configurações › Integrações › Novo token)
   - `EASYJUR_TOKEN` — token novo da API do EasyJur
4. Aba **Actions** › "Despachante do funil" › **Run workflow** com "Só simular"
   marcado. O resultado mostra o que ele faria, sem enviar nada.
5. Se a simulação estiver certa, ele passa a rodar sozinho (três plantões por
   dia, checando a cada minuto). Repositório **público** = minutos ilimitados e
   grátis. Atenção: o GitHub desliga agendamentos de repositório parado há 60
   dias; se isso acontecer, é só clicar em "Enable workflow".

## Segurança e privacidade

O repositório é público (é o que dá minutos ilimitados e gratuitos no GitHub
Actions). Por isso vale a regra: **nada de dado de cliente ou do escritório
pode entrar aqui**. O que garante isso:

- Os dados dos clientes nunca passam pelo GitHub. Ficam na Za.Ia, no EasyJur e
  no Google; o programa só os lê na hora, em memória, e descarta.
- O código e os testes não têm nome, telefone, e-mail nem caso real (os testes
  usam nomes e números inventados).
- O registro de execução (log) nunca escreve nome, telefone ou conteúdo de
  conversa. Como proteção extra, qualquer sequência que pareça telefone ou
  e-mail é mascarada automaticamente antes de sair, inclusive em mensagens de
  erro, e cada linha é cortada em 300 caracteres.
- Recomendado: em **Settings › Actions › General › Artifact and log retention**,
  colocar 1 dia, para o GitHub apagar os logs antigos sozinho.

- As chaves ficam só nos segredos do GitHub; o código não guarda nenhuma.
- O registro de execução (log) não mostra nome, telefone nem conversa de cliente.
- Para desligar: aba Actions › "Despachante do funil" › "Disable workflow".

## Lembretes, horário fora da oferta e comando GRAVAR

- Ao gravar uma reunião, o despachante agenda dois lembretes ao cliente: às 8h
  do dia (só quando a reunião é às 10h ou depois) e 1 hora antes.
- Lead que pede outro dia/hora depois da oferta (desde 23/10/2026): 1 minuto depois a
  automação manda **mais 2 horários livres**, respeitando o dia, o turno ou a hora que
  ele citou (até 2 vezes por oferta). Não vai nada ao grupo.
- **Exceção de horário** (noite, almoço, sábado/domingo, depois das 18h), **lead sem
  horário** (viajando, "essa semana não dá", "depois eu vejo"), lead que recusou as 2
  novas ofertas ou agenda sem vaga: 5 minutos depois da última mensagem dele, o
  advogado da oferta recebe no **privado** o que o lead disse, os próximos horários
  livres dele e os comandos prontos `OFERECER` e `GRAVAR`.
- Se a equipe propõe um horário fora da oferta e o lead aceita, sai no grupo
  "📌 HORÁRIO COMBINADO FORA DA OFERTA" com o comando pronto.
- Um advogado escreve no grupo (Firma 2026 ou AUTOMAÇÃO) **ou no privado dele com o
  escritório** `GRAVAR Hana 19/10 13h` (opcional: `com Fernanda`) e o despachante grava
  pessoa, oportunidade e atendimento no EasyJur, agenda os lembretes e confirma no
  mesmo canal, sem IA. O advogado padrão é o dono do privado ou o da última oferta.
- `OFERECER Ana 28/10 19h e 29/10 12h30` (grupo ou privado): manda ao lead esses
  horários, que podem ser fora do expediente ("o advogado separou um horário especial
  para você"). Antes confere se o advogado já tem compromisso nesse horário. Quando o
  lead escolhe, a reunião é gravada normalmente.
  Acrescente `presencial` (ex.: `GRAVAR Hana 19/10 13h presencial`) para gravar
  como atendimento no escritório.

## Atendimento presencial (desde 23/10/2026)

A oferta continua sendo **por videochamada**. Se depois dela o lead disser que
quer atendimento presencial ("presencial", "pessoalmente", "posso ir no
escritório?"), a conversa não para:

- A Annie já é orientada (Recepção, passo 1) a repetir os mesmos horários, agora
  presencial. Se em 3 minutos ninguém repetir os horários, o despachante manda
  "Claro, Fulano! O Dr. X pode te atender presencialmente, aqui no escritório,
  nos mesmos horários. Tenho estes horários: …" (só se nenhum humano da equipe
  tiver assumido a conversa).
- Quando o lead escolhe, a reunião é gravada como presencial: no EasyJur, local
  "Presencial — escritório"; confirmação, lembretes (8h e 1h antes) e aviso ao
  advogado dizem "aqui no escritório" e **não levam link**. O evento do Google
  Agenda do escritório continua sendo criado (título "Reunião PRESENCIAL …").
- "Não precisa ser presencial" ou "pode ser online" volta para videochamada.
- **Dr. Lucas só atende online.** Se o lead de uma oferta dele pedir presencial, o
  despachante (1 minuto depois) oferece os horários livres da **Dra. Danielle**,
  presencial, e avisa o grupo Firma 2026 ("🔁 PRESENCIAL COM A DRA. DANIELLE"). Nunca
  confirma presencial com o Dr. Lucas. Sem horário livre da Dra. Danielle, avisa o
  grupo ("📍 PRESENCIAL SEM HORÁRIO") para a equipe combinar.

## Google Agenda pelo despachante (ponte na conta do escritório)

Ao gravar uma reunião, o despachante cria o evento no Google Agenda do
escritório com link do Meet (convida a Dra. Fernanda ou o Dr. Lucas; a Dra.
Danielle não, porque usa Outlook), põe o link na descrição e no local do
atendimento no EasyJur, manda ao cliente a confirmação com o link, coloca o
link nos lembretes (8h e 1 hora antes) e avisa o advogado no privado.
Quando o cliente responde "sim/confirmo" ao lembrete de 1 hora antes, o
advogado recebe de novo o link no privado.

A ponte é o script `ponte_google_agenda.gs`, instalado UMA vez em
https://script.google.com com a conta do escritório:
1. Novo projeto › colar o conteúdo de `ponte_google_agenda.gs`.
2. Configurações do projeto › marcar "Mostrar arquivo de manifesto
   appsscript.json" › colar nele o conteúdo de `ponte_google_agenda.appsscript.json`.
3. Executar a função `configurar` › autorizar › copiar a chave mostrada no
   registro de execução.
4. Implantar › Nova implantação › App da Web › Executar como: eu · Quem pode
   acessar: qualquer pessoa › copiar o endereço do app.
5. No GitHub, Settings › Secrets › Actions: criar `GOOGLE_AGENDA_URL` (o
   endereço) e `GOOGLE_AGENDA_CHAVE` (a chave).
Sem esses dois segredos, nada quebra: o auditor continua criando o evento.

Sala aberta: o script tenta deixar a sala do Meet com acesso aberto (quem tem o
link entra sem pedir permissão). O aviso no grupo diz se conseguiu. Contas
Gmail comuns não permitem pôr o advogado como co-organizador da chamada.

## Depois da reunião: avaliação, resgate e comprovantes (desde 23/10/2026)

- **Avaliação no Google** (`despachante.py`, junto com o encerramento dos
  atendimentos concluídos, de hora em hora): atendimento marcado como Concluído no
  EasyJur → o cliente recebe uma vez o agradecimento com o link de avaliação do
  Google e as redes da Dra. Danielle (das 8h às 20h). Se o cliente estiver
  esperando resposta, espera; depois a conversa é encerrada como antes.
- **Resgate de reunião que não aconteceu** (`resgate.py`, de hora em hora, 8h–19h,
  seg–sex), para reunião de lead (atendimento com telefone na descrição) a partir
  de 23/10/2026, em dois casos: (1) o cliente recebeu o lembrete/pedido de
  confirmação do dia e NÃO respondeu nada até 2 horas depois do horário → R1 2 horas
  depois; (2) o cliente avisou no dia que não vai poder → R1 ("Sem problema...")
  15 minutos depois do aviso. O R1 traz 2 horários do mesmo advogado; se o cliente
  não marcar, a Annie volta a chamar 3, 5 e 10 dias úteis depois da data da reunião
  (R2, R3, R4 — o último diz que é a última mensagem), nunca antes de 2 dias úteis
  depois da última mensagem do cliente. A resposta do cliente segue o fluxo normal
  da oferta (escolha → gravação no EasyJur). Não entra: reunião cancelada pelo
  próprio advogado (sem lembrete no dia, ou o escritório avisou cancelamento antes
  do cliente), cliente que confirmou, equipe falando com o cliente, contrato,
  desistência, atendimento concluído ou reunião nova. O advogado recebe 📵 no
  privado no R1 e um aviso final 5 dias úteis depois do R4.
- **Lead parado na triagem** (`followup_lead.py`, a cada 15 min, 8h–20h, desde
  26/10/2026, caso Edson): conversa de lead novo (criada há até 14 dias, status
  OPEN, sem ninguém da equipe escrevendo há 30 dias, sem oferta de horários) cuja
  última mensagem é uma pergunta da Annie e o lead não respondeu → a Annie chama de
  novo: F1 1 hora depois ("Ainda está por aí?"), F2 no dia seguinte e F3 3 dias
  depois (última mensagem). Pergunta com mais de 3 dias sem follow-up não começa.
  Quando o lead responde, a Annie continua o roteiro. A retomada (Annie sem pergunta,
  2–4 min) não dispara mais em conversa de cliente já atendido pela equipe.
- **Sinal da pós-reunião** (`porteiro.avisar_posreuniao`, arquivo `posreuniao.json`
  no ramo "sinal", só hora e tipo): o despachante avisa quando há novidade —
  link do ZapSign na conversa, arquivo novo de cliente com reunião recente,
  reunião concluída no EasyJur, lista/encerramento de documentos de advogado no
  Firma 2026 e tarefa "Revisão da documentação" concluída. A rotina pós-reunião
  (Claude) só roda inteira na rodada das 9h ou quando há esse sinal ou e-mail novo
  de assinatura do ZapSign; nas outras rodadas encerra em segundos.
- **Comprovante de cliente** (`comprovantes.py`, a cada 5 min): imagem/PDF que a
  Za.Ia descreve como Pix/transferência/depósito para o escritório (Dra. Danielle,
  Dr. Lucas ou Dra. Fernanda como recebedor; ou sem recebedor legível quando o
  cliente fala em pagamento) → aviso "🧾 COMPROVANTE DE CLIENTE" no grupo
  Financeiro Escritório, sem CPF/agência/conta, e a rotina financeira é acordada.
  A rotina confere o cadastro e as receitas do cliente no EasyJur, diz qual parcela
  bate com o valor e publica o rascunho F; nada é lançado sem o OK de um advogado.
  Comprovante de salário/compra (recebedor de fora) é ignorado.

## Secretaria sem IA (`secretaria.py`)

Roda dentro do mesmo plantão, a cada 2 minutos, e substitui duas rotinas com IA:

- **Comandos do resumo matinal** (Dra. Fernanda e Dra. Danielle, no privado do
  escritório): `LIDA 1 3 A2`, `LIDA TODAS`, `MANTER 2`, `PRAZO 2 13/10 texto`,
  `TAREFA 4 05/10 texto`, `AGENDAR 10/10 14h assunto`, `MINHA AGENDA`,
  `AGENDA Lucas`. No PRAZO o advogado escolhe as duas datas: `PRAZO 2 fatal 29/10
  interno 27/10 texto` (ou `PRAZO 2 29/10 27/10`: a maior é a fatal). Com uma data só,
  ela é a fatal e a interna fica 2 dias úteis antes. Desde 23/10 o LIDA confere no
  EasyJur se a publicação/andamento ficou marcado como lido e avisa ⚠️ se não ficou
  (itens 🔖 E- são avisos só do PJe: não existem no EasyJur para marcar).
- **Aprovações do relatório de pendências do Dr. Lucas**: `OK 2`, `OK 1 3`,
  `OK TODAS`, `EDITAR 2: texto`, `NÃO 2`.
- **Aviso ao cliente** (os três advogados): `CLIENTE 1 A2` envia ao cliente o
  rascunho "📲 Para o cliente" do item; `CLIENTE 3: texto` envia o texto do
  advogado; `CLIENTE TODOS` (itens do resumo) e `CLIENTE T TODOS` (retorno
  mensal). Sai assinado pelo advogado. Item já enviado não sai de novo.

## Acompanhamento de clientes (desde 20/10/2026)

1. **Andamento ou publicação**: o resumo matinal (rotina com IA, 7h30) põe, em
   cada item com cliente do escritório, um rascunho em linguagem simples para o
   cliente. Nada sai sem `CLIENTE n` do advogado.
2. **Retorno mensal** (`retorno.py`, sem IA): de segunda a sexta, entre 9h e 11h,
   pega a fatia do dia dos clientes com processo ativo (cada cliente cai num dia a
   cada 20 dias úteis). Quem não recebeu mensagem assinada por advogado nos
   últimos 25 dias entra numa lista "🗓️ Retorno mensal aos clientes" (itens T1,
   T2...) enviada ao advogado responsável, com rascunho montado da última
   movimentação. Custo: ~8 chamadas ao EasyJur por dia.

Só entende esses formatos exatos; qualquer outra frase fica para o assistente
com IA. Cada comando é executado uma vez: a resposta leva a marca `#número` da
mensagem do comando. Áudio não é tratado aqui. Só baixa a conversa inteira
quando chegou mensagem nova (confere antes a hora da última mensagem).

## Parcelas do mês (`recebimentos.py`, desde 21/10/2026)

No 1º dia útil de cada mês (8h de Belém; nova tentativa às 11h), o workflow
"Parcelas do mês" lê no EasyJur as receitas em aberto e manda ao grupo
"Financeiro Escritório" uma planilha .xlsx com duas abas: as parcelas que vencem
no mês (vencimento, cliente, valor, parcela x/y, especificação, advogado, forma
de pagamento, situação e nº da receita) e as **atrasadas de meses anteriores**
(com dias em atraso), cada uma com total. Junto vai um resumo com o total por
semana, por advogado e das atrasadas. O advogado vem do filtro `id_advogado` da
listagem (a listagem em si não traz o campo); receita sem advogado aparece com
"—". Se a Za.Ia recusar o arquivo no grupo, a mesma lista vai em texto. Não
repete no mês (procura o resumo "📊 Parcelas a receber — mês/ano" no grupo).
Para mandar de novo ou ver outro mês: Actions → "Parcelas do mês" → Run
workflow, mês `AAAA-MM` (com "prévia" marcado, não conta como o envio oficial).
Custo: ~55 chamadas ao EasyJur por mês. A planilha é montada em memória; nada
fica no repositório nem no log. O arquivo vai pelo `enviar_midia`, que só aceita
número: o código usa o ID de WhatsApp do grupo guardado no contato "Financeiro
Escritório" da Za.Ia, e o upload precisa de User-Agent próprio (Cloudflare).

## Porteiro (`porteiro.py`)

Também no plantão, a cada 2 minutos. Olha o privado dos 3 advogados e os grupos
"Firma 2026" e "AUTOMAÇÃO Firma". Quando chega pedido novo de advogado que a
secretaria sem IA não resolve (texto livre, OK S3, EDITAR R2, comprovante,
áudio), grava a hora no arquivo `sinal.json` do ramo `sinal` (só a hora, sem
nenhum dado). As rotinas do Claude "Secretário geral" e "Respostas pelo grupo"
leem esse arquivo no primeiro passo e encerram na hora se não houver pedido
novo; assim a rodada vazia quase não gasta. Em grupo, só conta mensagem de
advogado dirigida ao sistema (verbo de ordem, código ou menção ao assistente).
Pedido de mensagem programada ao cliente ("quero agendar uma mensagem para…") também conta.
Teste manual: Actions › "Gravar sinal para o Claude (teste manual)" › Run workflow.

Grupo "Financeiro Escritório" (claude-grupo-18, desde 20/10/2026): qualquer mensagem
de advogado ali grava a hora em `financeiro.json` (mesmo ramo), que só a rotina
financeira lê. Assim a conversa do financeiro não acorda o Secretário nem as Respostas.

O porteiro também grava, a cada 5 minutos, o arquivo `despesas.json` no mesmo ramo
`sinal`: a lista de códigos de despesas e repasses já aprovados no grupo Financeiro
Escritório (ou, para os antigos, no AUTOMAÇÃO)
("✅ F7 despesa aprovada…") e ainda não lançados ("🧾 F7 de 19/10 lançada…"). Só
códigos, sem nenhum dado. A tarefa noturna do computador do escritório (22h) lê esse
arquivo e só abre o EasyJur no Chrome quando a lista não está vazia.

**Aviso da manhã no grupo do financeiro (desde 22/10/2026).** Nos dias úteis, a
partir das 8h, o porteiro manda uma vez ao grupo Financeiro Escritório a lista
"⏰ Pendências do financeiro — DD/MM" com: despesas aprovadas que nenhum lançamento
das 22h confirmou com 🧾 (separando as que já deviam ter entrado das aprovadas depois
das 22h da véspera) e rascunhos F parados há mais de 2 h sem resposta de advogado nem
decisão (✅/⏭️/🧾), dizendo o que falta. Sem pendência, não manda nada. Nasceu do caso
de 21/10: F4 ficou esperando a forma de pagamento sem ninguém lembrar, e F5/F6 ficaram
"aprovadas" no grupo enquanto o lançamento da noite avisava só o Dr. Lucas no privado.

## Consumo da API do EasyJur (cota mensal de 10.000 chamadas)

- O despachante lê a Za.Ia a cada minuto, mas só chama o EasyJur quando precisa:
  ao montar uma oferta de horários, ao gravar uma reunião confirmada e, uma vez
  por hora (7h–19h), ao conferir atendimentos concluídos. Uso normal: ~40
  chamadas por dia.
- Trava de segurança: no máximo `EASYJUR_MAX_HORA` chamadas por hora (padrão 80,
  janela móvel) e `EASYJUR_MAX_PLANTAO` por plantão (padrão 250). Se estourar, ele
  avisa o Dr. Lucas no privado e espera só até a janela liberar; a leitura do WhatsApp
  continua e o que ficou pendente sai logo depois.
- Se a gravação de uma reunião confirmada falhar, ele avisa o Dr. Lucas no privado uma vez
  ("NÃO CONSEGUI GRAVAR A REUNIÃO") e não tenta de novo sozinho (antes ele repetia
  a cada minuto e gastava a cota).
- Cota mensal esgotada (erro 429): ele espera 60 minutos antes de tentar de novo.
- O resumo de cada rodada no log mostra `easyjur_no_plantao`, o total de
  chamadas feitas no plantão.

## Erros da automação vão só ao Dr. Lucas (desde 19/10/2026)

O Dr. Lucas é o responsável por corrigir os erros da automação. Por isso os avisos de
erro do despachante (EasyJur pausado, reunião que não deu para gravar) e os defeitos
encontrados pelo auditor vão só para o privado dele. Os grupos ficam como informe do
que acontece nos contatos da Za.Ia; o auditor manda no máximo 4 informes por dia.

## Regras de agenda (iguais às das rotinas)

- Dra. Danielle: seg–qui, 10h00–11h00 e 14h00–17h00 (meia em meia hora).
- Dra. Fernanda: seg–qui, 09h30, 10h30, 14h30 e 15h30; dia com audiência fica bloqueado.
- Dr. Lucas: seg–qui, 10h30–16h30.
- Ninguém na sexta, fim de semana ou feriado do escritório. Mínimo de 3 horas
  de antecedência. Só compromissos reais ocupam; VIAGEM sem hora bloqueia o dia.
