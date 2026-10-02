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

## Segurança

- As chaves ficam só nos segredos do GitHub; o código não guarda nenhuma.
- O registro de execução (log) não mostra nome, telefone nem conversa de cliente.
- Para desligar: aba Actions › "Despachante do funil" › "Disable workflow".

## Regras de agenda (iguais às das rotinas)

- Dra. Danielle: seg–qui, 10h00–11h00 e 14h00–17h00 (meia em meia hora).
- Dra. Fernanda: seg–qui, 09h30 e 14h30; dia com audiência fica bloqueado.
- Dr. Lucas: seg–qui, 10h30–16h30.
- Ninguém na sexta, fim de semana ou feriado do escritório. Mínimo de 3 horas
  de antecedência. Só compromissos reais ocupam; VIAGEM sem hora bloqueia o dia.
