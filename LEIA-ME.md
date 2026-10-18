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

## Secretaria sem IA (`secretaria.py`)

Roda dentro do mesmo plantão, a cada 2 minutos, e substitui duas rotinas com IA:

- **Comandos do resumo matinal** (Dra. Fernanda e Dra. Danielle, no privado do
  escritório): `LIDA 1 3 A2`, `LIDA TODAS`, `MANTER 2`, `PRAZO 2 13/10 texto`,
  `TAREFA 4 05/10 texto`, `AGENDAR 10/10 14h assunto`, `MINHA AGENDA`,
  `AGENDA Lucas`. PRAZO cria a data interna 2 dias úteis antes da fatal.
- **Aprovações do relatório de pendências do Dr. Lucas**: `OK 2`, `OK 1 3`,
  `OK TODAS`, `EDITAR 2: texto`, `NÃO 2`.

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

## Consumo da API do EasyJur (cota mensal de 10.000 chamadas)

- O despachante lê a Za.Ia a cada minuto, mas só chama o EasyJur quando precisa:
  ao montar uma oferta de horários, ao gravar uma reunião confirmada e, uma vez
  por hora (7h–19h), ao conferir atendimentos concluídos. Uso normal: ~40
  chamadas por dia.
- Trava de segurança: no máximo `EASYJUR_MAX_HORA` chamadas por hora (padrão 80,
  janela móvel) e `EASYJUR_MAX_PLANTAO` por plantão (padrão 250). Se estourar, ele
  avisa o grupo AUTOMAÇÃO e espera só até a janela liberar; a leitura do WhatsApp
  continua e o que ficou pendente sai logo depois.
- Se a gravação de uma reunião confirmada falhar, ele avisa o grupo uma vez
  ("NÃO CONSEGUI GRAVAR A REUNIÃO") e não tenta de novo sozinho (antes ele repetia
  a cada minuto e gastava a cota).
- Cota mensal esgotada (erro 429): ele espera 60 minutos antes de tentar de novo.
- O resumo de cada rodada no log mostra `easyjur_no_plantao`, o total de
  chamadas feitas no plantão.

## Regras de agenda (iguais às das rotinas)

- Dra. Danielle: seg–qui, 10h00–11h00 e 14h00–17h00 (meia em meia hora).
- Dra. Fernanda: seg–qui, 09h30 e 14h30; dia com audiência fica bloqueado.
- Dr. Lucas: seg–qui, 10h30–16h30.
- Ninguém na sexta, fim de semana ou feriado do escritório. Mínimo de 3 horas
  de antecedência. Só compromissos reais ocupam; VIAGEM sem hora bloqueia o dia.
