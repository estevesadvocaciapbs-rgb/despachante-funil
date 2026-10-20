# Despachante do funil — Esteves Advocacia

Programa pequeno, **sem IA**, que fica de plantão no GitHub das 7h às 21h e
confere a Za.Ia **a cada 60 segundos**. Quando um lead triado aparece (tarefa ou
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
- Lead que pede outro dia/hora depois da oferta gera no grupo Firma 2026 o aviso
  "🕐 LEAD PEDIU OUTRO HORÁRIO".
- Se a equipe propõe um horário fora da oferta e o lead aceita, sai no grupo
  "📌 HORÁRIO COMBINADO FORA DA OFERTA" com o comando pronto.
- Um advogado escreve no grupo (Firma 2026 ou AUTOMAÇÃO) `GRAVAR Hana 19/10 13h`
  (opcional: `com Fernanda`) e o despachante grava pessoa, oportunidade e
  atendimento no EasyJur, agenda os lembretes e confirma no grupo, sem IA.
  O advogado padrão é o da última oferta feita ao lead.

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

## Secretaria sem IA (`secretaria.py`)

Roda dentro do mesmo plantão, a cada 2 minutos, e substitui duas rotinas com IA:

- **Comandos do resumo matinal** (Dra. Fernanda e Dra. Danielle, no privado do
  escritório): `LIDA 1 3 A2`, `LIDA TODAS`, `MANTER 2`, `PRAZO 2 13/10 texto`,
  `TAREFA 4 05/10 texto`, `AGENDAR 10/10 14h assunto`, `MINHA AGENDA`,
  `AGENDA Lucas`. PRAZO cria a data interna 2 dias úteis antes da fatal.
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

## Porteiro (`porteiro.py`)

Também no plantão, a cada 2 minutos. Olha o privado dos 3 advogados e os grupos
"Firma 2026" e "AUTOMAÇÃO Firma". Quando chega pedido novo de advogado que a
secretaria sem IA não resolve (texto livre, OK S3, EDITAR R2, comprovante,
áudio), grava a hora no arquivo `sinal.json` do ramo `sinal` (só a hora, sem
nenhum dado). As rotinas do Claude "Secretário geral" e "Respostas pelo grupo"
leem esse arquivo no primeiro passo e encerram na hora se não houver pedido
novo; assim a rodada vazia quase não gasta. Em grupo, só conta mensagem de
advogado dirigida ao sistema (verbo de ordem, código ou menção ao assistente).
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
- Dra. Fernanda: seg–qui, 09h30 e 14h30; dia com audiência fica bloqueado.
- Dr. Lucas: seg–qui, 10h30–16h30.
- Ninguém na sexta, fim de semana ou feriado do escritório. Mínimo de 3 horas
  de antecedência. Só compromissos reais ocupam; VIAGEM sem hora bloqueia o dia.
