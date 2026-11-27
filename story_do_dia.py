"""Story do dia (pedido do Dr. Lucas em 27/11/2026): ideia pronta de story leve no WhatsApp dele.

Ele quer postar mais nos Stories, de forma leve e pessoal, e nunca sabe o que gravar na hora. O despachante manda
uma ideia por horário: dias úteis 7h30, 14h e 19h; sábado e domingo 9h e 19h (Belém). Cada ideia traz o que
gravar, o texto na tela e o sticker. Sem IA: o banco de ideias é fixo e roda por data (a mesma ideia só volta
depois de passar pelas outras). Repositório PÚBLICO: aqui não entra dado de cliente.

Rodar: python story_do_dia.py [--simular] [--periodo manha|tarde|noite]
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
LUCAS_TEL = "5524992432455"

# (o que gravar, texto na tela, sticker)
MANHA = [
    ("Foto da xícara de café na mesa.", "Primeiro café do dia. E o seu?", "Enquete: Já tomei / Nem tomei ainda"),
    ("Vídeo de 10 s da rua a caminho do escritório (com o carro parado ou a pé).", "Bom dia, Parauapebas",
     "Localização"),
    ("Selfie de 15 s dizendo em uma frase o que vem pela frente hoje.", "Bora",
     "Emoji deslizante: Nível de animação para hoje"),
    ("Foto do céu agora.", "Hoje o dia vai ser de quê?", "Enquete: Sol forte / Chuva"),
    ("Celular na mesa tocando a música que você ouviu vindo para cá.", "Trilha de hoje",
     "Música + caixinha: Manda a sua"),
    ("Foto do livro que você está lendo, em cima da mesa.", "Lendo agora", "Caixinha: Me indica um livro"),
    ("Timelapse de 10 s arrumando a mesa antes de começar.", "Começando", "Enquete: Mesa arrumada / Caos criativo"),
    ("Foto do café da manhã ou da padaria.", "Café da manhã de hoje", "Enquete: Tapioca / Pão na chapa"),
    ("Selfie andando até a sala, falando bom dia como quem fala com um amigo.", "Bom dia",
     "Caixinha: Como começou o seu dia?"),
    ("Foto do treino ou da caminhada, se teve.", "Antes do trabalho", "Enquete: Treina de manhã / À noite"),
    ("Foto da lista de 3 coisas do dia escrita à mão (sem nome de cliente).", "As 3 de hoje",
     "Caixinha: Qual a sua prioridade de hoje?"),
]
TARDE = [
    ("Foto do prato do almoço.", "Almoço de hoje", "Enquete: Marmita / Restaurante"),
    ("Foto da tela com o assunto que você está estudando, desfocada (nenhum nome ou processo legível).",
     "Adivinha o que estou estudando", "Quiz: Imposto de Renda / Reforma tributária / MEI"),
    ("Celular apoiado gravando timelapse de 1 hora de trabalho.", "Modo foco", "Emoji deslizante: Nível de foco"),
    ("Selfie de 15 s contando uma coisa que você aprendeu hoje (de trabalho ou não).", "Coisa que aprendi hoje",
     "Caixinha: E você, aprendeu o quê?"),
    ("Foto do café ou do lanche da tarde.", "Pausa das 15h", "Enquete: Café / Açaí"),
    ("Foto da janela ou da vista de onde você está.", "Vista de quem está trabalhando",
     "Enquete: Trabalha em casa / Fora"),
    ("Foto do caderno com anotações à mão (sem nome de cliente).", "Ainda anoto tudo no papel",
     "Enquete: Papel / Celular"),
    ("Selfie com uma pergunta rápida.", "Pix ou dinheiro?", "Enquete: Pix / Dinheiro"),
    ("Foto da pilha de livros ou do material da tarde.", "Material de hoje",
     "Emoji deslizante: Peso da leitura de hoje"),
    ("Selfie com cara de quem pensa.", "Mito ou verdade? Advogado só trabalha de terno",
     "Quiz: Mito / Verdade"),
    ("Foto da sala vazia antes de uma reunião (sem pessoas e sem papéis à vista).", "Preparando a próxima conversa",
     "Emoji deslizante: Cafés até agora"),
]
NOITE = [
    ("Vídeo de 5 s apagando a luz ou fechando a porta do escritório.", "Encerrado por hoje",
     "Enquete: Já encerrei / Ainda não"),
    ("Foto do jantar.", "Janta de hoje", "Caixinha: Sugestão de janta para amanhã?"),
    ("Foto da TV com a série ou o filme da noite.", "Assistindo agora", "Enquete: Já vi / Não conheço"),
    ("Selfie resumindo o dia em 3 palavras.", "Meu dia em 3 palavras", "Caixinha: E o seu?"),
    ("Responda em selfie 1 ou 2 perguntas que chegaram na caixinha (se chegou alguma).", "Vocês perguntaram",
     "Caixinha nova: Pergunta qualquer coisa"),
    ("Foto do céu no fim da tarde.", "Fim de dia em Parauapebas", "Localização"),
    ("Foto do livro de cabeceira.", "Leitura da noite", "Caixinha: O que você está lendo?"),
    ("Foto ou vídeo curto do treino da noite, se teve.", "Treino feito", "Emoji deslizante: Cansaço"),
    ("Celular tocando a música do fim do dia.", "Para fechar o dia", "Música"),
    ("Selfie com uma pergunta leve.", "Você é de dormir cedo ou tarde?", "Enquete: Cedo / Tarde"),
    ("Selfie de 10 s contando uma coisa boa que aconteceu hoje.", "A melhor parte de hoje",
     "Caixinha: E a sua?"),
]
FIM_DE_SEMANA = [
    ("Foto do café da manhã de sábado ou domingo, sem pressa.", "Sem despertador hoje",
     "Enquete: Acordou cedo / Dormiu até tarde"),
    ("Vídeo de 10 s do passeio, da feira ou do lugar onde você está.", "Fim de semana", "Localização"),
    ("Foto da comida que você está fazendo ou vai comer.", "Cozinhando hoje", "Caixinha: Me passa uma receita"),
    ("Selfie sem terno, roupa de fim de semana.", "Versão sábado", "Emoji deslizante: Nível de descanso"),
    ("Foto do jogo, do esporte ou do que você está vendo.", "Hoje é dia de", "Enquete: Assiste / Pratica"),
    ("Foto da rede, do sofá ou do lugar preferido da casa.", "Modo descanso", "Enquete: Descansar / Sair"),
    ("Selfie com uma pergunta leve.", "O que você mais gosta de fazer no fim de semana?", "Caixinha"),
]
DATAS = {  # (mês, dia) -> ideia da noite no lugar da rotação
    (12, 24): ("Foto da mesa da ceia ou da decoração.", "Feliz Natal", "Emoji deslizante: Fome"),
    (12, 25): ("Foto do almoço de Natal.", "Natal em família", "Caixinha: O que teve aí?"),
    (12, 31): ("Selfie contando uma coisa boa de 2026.", "O melhor do ano", "Caixinha: E o seu?"),
    (1, 1): ("Foto do céu do primeiro dia do ano.", "Começando 2027", "Caixinha: Uma meta para este ano"),
}
TITULO = {"manha": "da manhã", "tarde": "da tarde", "noite": "da noite"}


def _log(msg):
    print(f"[story-do-dia] {msg}", flush=True)


def periodo(local):
    if local.hour < 11:
        return "manha"
    return "tarde" if local.hour < 17 else "noite"


def ideia(dia, per):
    fds = dia.weekday() >= 5
    if per == "noite" and (dia.month, dia.day) in DATAS:
        return DATAS[(dia.month, dia.day)]
    if fds and per == "manha":
        banco = FIM_DE_SEMANA
    else:
        banco = {"manha": MANHA, "tarde": TARDE, "noite": NOITE}[per]
    return banco[dia.toordinal() % len(banco)]


def texto(dia, per):
    gravar, tela, sticker = ideia(dia, per)
    return (f"📱 *Story {TITULO[per]}*\n"
            f"Grave: {gravar}\n"
            f"Texto na tela: {tela}\n"
            f"Sticker: {sticker}\n\n"
            "Celular na mão, sem arte e sem edição. Se não der agora, pule.")


def main(argv):
    agora = datetime.now(timezone.utc).astimezone(BRT)
    per = argv[argv.index("--periodo") + 1] if "--periodo" in argv else periodo(agora)
    msg = texto(agora.date(), per)
    if "--simular" in argv:
        print(msg)
        return
    import despachante
    from funil_semanal import _z
    zaia = despachante.MCP(despachante.ZAIA_URL, os.environ.get("ZAIA_TOKEN"), "Za.Ia")
    _z(zaia, "enviar_mensagem", assinatura="ia", numero=LUCAS_TEL, texto=msg)
    _log(f"enviada a ideia {per} de {agora:%d/%m}")


if __name__ == "__main__":
    main(sys.argv[1:])
