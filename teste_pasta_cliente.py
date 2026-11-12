"""Testes dos arquivos do cliente para a pasta do Drive (dados fictícios; pedido de 12/11/2026)."""
from datetime import datetime, timedelta, timezone

import agenda_google
import aviso_documento as ad
import despachante as d
import pasta_cliente as pc
import porteiro

AGORA = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)
CLI = "5500000000011"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Ponte:
    """Faz o papel da ponte do Google (Apps Script)."""
    def __init__(self, pastas=(), status="movido"):
        self.pastas, self.status, self.chamadas = list(pastas), status, []

    def procurar(self, nome, area=None):
        return [p for p in self.pastas if all(w in p["caminho"].lower() for w in nome.split())]

    def guardar(self, tel, de, ate, nome, area=None, escolha=None, criar=False, nome_pasta=""):
        self.chamadas.append(dict(tel=tel, de=de, ate=ate, nome=nome, area=area, escolha=escolha, criar=criar,
                                  nome_pasta=nome_pasta))
        cand = self.procurar(nome)
        if escolha:
            cand = cand[escolha - 1:escolha]
        if len(cand) > 1:
            return {"status": "varias", "candidatos": cand}
        if cand:
            return {"status": "movido", "caminho": cand[0]["caminho"] + " › Docs de Prova", "n": 2, "criada": False}
        if criar:
            return {"status": "movido", "caminho": f"Processos › {area} › {nome_pasta} › Docs de Prova", "n": 2,
                    "criada": True}
        return {"status": "nenhuma"}


def liga(ponte):
    agenda_google.configurado = lambda: True
    agenda_google.procurar_pasta = ponte.procurar
    agenda_google.guardar_arquivos = ponte.guardar


class Z:
    def __init__(self, privado):
        self.privado, self.env = privado, []

    def chamar(self, f, **a):
        self.env.append((f, a))
        if f == "buscar_conversa_por_telefone":
            return {"conversa": {"id": "priv-" + a["telefone"]}}
        if f == "ler_conversa":
            return {"messages": self.privado if a["conversaId"] == "priv-" + d.DANIELLE["tel"] else []}
        return {}

    def enviados(self):
        return [a["texto"] for f, a in self.env if f == "enviar_mensagem"]


def aviso(codigo, criado, bloco):
    return {"id": f"av{codigo}", "sender": "AI", "createdAt": iso(criado),
            "content": f"📎 *DOCUMENTO DE CLIENTE — Ana Souza ({CLI})*\nChegaram 2 arquivos pelo WhatsApp em "
                       f"12/11 13:00 a 13:05:\n• Foto: RG\n• PDF/arquivo: CTPS.pdf\n(último às 12/11 13:05)\n"
                       f"👉 Os arquivos estão na conversa do cliente na Za.Ia.\n\n{bloco}"}


def resposta(texto, quando, n=1):
    return {"id": f"r{n}", "sender": "CONTACT", "createdAt": iso(quando), "content": texto}


def zera():
    pc._estado["ultima"] = None
    pc._feito.clear()


# 1) nome do contato vira as palavras do nome
assert pc.nome_limpo("Wellington Souza Cliente Fernanda", d) == "wellington souza"
assert pc.nome_limpo("Rubemar Criminal Fernanda", d) == "rubemar"
assert pc.nome_limpo("Pedro Lucas Silva", d) == "pedro lucas silva"
assert pc.nome_da_pasta("joão da silva cliente fernanda", "TRABALHISTA", d.FERNANDA, d) == "Joao da Silva - FERNANDA"
assert porteiro.resolvido_pelo_codigo("NÃO PASTA D3", "dani") and porteiro.resolvido_pelo_codigo("Pasta D12 família", "lucas")
print("OK — nome do contato limpo e respostas PASTA não acordam a IA")

# 2) bloco do aviso conforme a situação
cli_msgs = [{"sender": "CONTACT", "createdAt": iso(AGORA - timedelta(hours=1)), "content": "oi"}]
pedido = [{"sender": "USER", "createdAt": iso(AGORA - timedelta(days=3)),
           "content": "Seja bem-vinda! Para darmos andamento, envie por aqui a lista de documentos abaixo: RG, CTPS"}]
liga(Ponte([{"id": "p1", "caminho": "Processos › TRABALHISTA › Ana Souza Lima"}]))
b = pc.bloco_aviso(4, "Ana Souza Cliente", {"id": "c1"}, cli_msgs, [], d.DANIELLE, AGORA, d)
assert "📂 *D4*" in b and "vou guardar em Processos › TRABALHISTA › Ana Souza Lima › Docs de Prova às 16:00" in b, b
liga(Ponte([]))
b = pc.bloco_aviso(5, "Ana Souza", {"id": "c1"}, cli_msgs + pedido, [], d.DANIELLE, AGORA, d)
assert "vou criar a pasta Processos › TRABALHISTA › Ana Souza e guardar" in b, b
b = pc.bloco_aviso(6, "Ana Souza", {"id": "c1"}, cli_msgs, [], d.DANIELLE, AGORA, d)
assert "não achei a pasta" in b and "vou" not in b, b
b = pc.bloco_aviso(7, "Ana", {"id": "c1"}, cli_msgs, [], d.DANIELLE, AGORA, d)
assert "salvo só como" in b, b
liga(Ponte([{"id": "p1", "caminho": "Processos › TRABALHISTA › Ana Souza"},
            {"id": "p2", "caminho": "Processos › CÍVEL › Ana Souza Reis"}]))
b = pc.bloco_aviso(8, "Ana Souza", {"id": "c1"}, cli_msgs, [], d.DANIELLE, AGORA, d)
assert "1) Processos › TRABALHISTA › Ana Souza" in b and "PASTA D8 1" in b, b
print("OK — aviso diz para onde vão os arquivos (pasta achada, pasta nova, sem pasta, nome curto, várias)")

# 3) guarda sozinho 1 hora depois; não repete
ponte = Ponte([{"id": "p1", "caminho": "Processos › TRABALHISTA › Ana Souza Lima"}])
liga(ponte)
av = aviso(1, AGORA - timedelta(minutes=70), "📂 *D1* — vou guardar em Processos › TRABALHISTA › Ana Souza Lima "
                                               "› Docs de Prova às 13:10.")
z = Z([av])
zera()
pc.rodada(z, AGORA, {}, d)
assert len(ponte.chamadas) == 1 and z.enviados()[0].startswith("✅ *D1* guardado: 2 arquivo(s)"), z.enviados()
c = ponte.chamadas[0]
assert c["tel"] == CLI and c["de"] == datetime(2026, 11, 12, 15, 50, tzinfo=timezone.utc) \
    and c["ate"] == datetime(2026, 11, 12, 16, 35, tzinfo=timezone.utc), c
z.privado.append({"id": "m1", "sender": "AI", "createdAt": iso(AGORA), "content": z.enviados()[0]})
zera()
pc.rodada(z, AGORA + timedelta(minutes=10), {}, d)
assert len(ponte.chamadas) == 1, "não pode guardar de novo depois do ✅"
# antes de 1 hora não guarda
ponte.chamadas.clear()
z = Z([aviso(2, AGORA - timedelta(minutes=30), "📂 *D2* — vou guardar em X às 18:30.")])
zera()
pc.rodada(z, AGORA, {}, d)
assert not ponte.chamadas and not z.enviados()
print("OK — guarda sozinho 1 hora depois do aviso, com a janela certa, e não repete")

# 4) NÃO PASTA D2 impede; PASTA D2 guarda na hora; NÃO depois do ✅ só informa
z = Z([aviso(2, AGORA - timedelta(minutes=90), "📂 *D2* — vou guardar em X às 17:30."),
       resposta("Não pasta D2", AGORA - timedelta(minutes=80))])
zera()
pc.rodada(z, AGORA, {}, d)
assert not ponte.chamadas and z.enviados() == ["👍 *D2*: combinado, não guardo estes arquivos na pasta."], z.enviados()
z = Z([aviso(3, AGORA - timedelta(minutes=5), "📂 *D3* — vou guardar em X às 18:55."),
       resposta("PASTA D3", AGORA - timedelta(minutes=2))])
zera()
pc.rodada(z, AGORA, {}, d)
assert len(ponte.chamadas) == 1 and z.enviados()[0].startswith("✅ *D3*"), z.enviados()
z = Z([aviso(4, AGORA - timedelta(hours=3), "📂 *D4* — vou guardar em X às 16:00."),
       {"id": "m", "sender": "AI", "createdAt": iso(AGORA - timedelta(hours=2)), "content": "✅ *D4* guardado: 2"},
       resposta("nao pasta d4", AGORA - timedelta(minutes=3))])
zera()
pc.rodada(z, AGORA, {}, d)
assert z.enviados() and z.enviados()[0].startswith("👍 *D4*: os arquivos já estavam guardados"), z.enviados()
print("OK — NÃO PASTA impede, PASTA guarda na hora, NÃO depois de guardado só informa")

# 5) sem pasta e sem pedido: espera o advogado; pasta nova só no caso pós-reunião; várias pastas: escolha
ponte = Ponte([])
liga(ponte)
z = Z([aviso(5, AGORA - timedelta(hours=2), "📂 *D5* — não achei a pasta deste cliente em Processos.")])
zera()
pc.rodada(z, AGORA, {}, d)
assert not ponte.chamadas and not z.enviados(), "sem pasta e sem resposta: não faz nada sozinho"
z = Z([aviso(6, AGORA - timedelta(hours=2), "📂 *D6* — o cliente ainda não tem pasta. Como os documentos foram "
                                            "pedidos depois da reunião, vou criar a pasta Processos › TRABALHISTA › "
                                            "Ana Souza e guardar às 17:00.")])
zera()
pc.rodada(z, AGORA, {}, d)
assert ponte.chamadas[-1]["criar"] and ponte.chamadas[-1]["area"] == "TRABALHISTA", ponte.chamadas
assert "Pasta nova criada" in z.enviados()[0], z.enviados()
z = Z([aviso(7, AGORA - timedelta(minutes=10), "📂 *D7* — o cliente ainda não tem pasta. Como os documentos foram "
                                               "pedidos depois da reunião, vou criar a pasta Processos › TRABALHISTA › "
                                               "Ana Souza e guardar às 18:50."),
       resposta("PASTA D7 família", AGORA - timedelta(minutes=5))])
zera()
pc.rodada(z, AGORA, {}, d)
assert ponte.chamadas[-1]["area"] == "FAMÍLIA" and ponte.chamadas[-1]["nome_pasta"] == "Ana Souza", ponte.chamadas[-1]
ponte = Ponte([{"id": "p1", "caminho": "Processos › TRABALHISTA › Ana Souza"},
               {"id": "p2", "caminho": "Processos › CÍVEL › Ana Souza Reis"}])
liga(ponte)
z = Z([aviso(8, AGORA - timedelta(minutes=10), "📂 *D8* — achei mais de uma pasta com esse nome:\n1) a\n2) b"),
       resposta("PASTA D8 2", AGORA - timedelta(minutes=5))])
zera()
pc.rodada(z, AGORA, {}, d)
assert ponte.chamadas[-1]["escolha"] == 2 and "CÍVEL" in z.enviados()[0], z.enviados()
print("OK — sem pasta espera o advogado; pasta nova só no pós-reunião (área trocável); escolha entre várias")

# 6) o aviso de documento ganha o bloco com o código seguinte
liga(Ponte([{"id": "p1", "caminho": "Processos › FAMÍLIA › Ana Souza Lima"}]))
from teste_aviso_documento import Z as ZA, zera as zera_ad, AGORA as AG
zera_ad()
priv = [{"sender": "AI", "createdAt": "2026-11-01T10:00:00.000Z", "content": "antigo 📂 *D3* — x"}]
za = ZA(nome="Ana Souza Cliente Fernanda", privado=priv)
ad.rodada(za, AG, {}, d, [])
txt = [a["texto"] for f, a in za.env if f == "enviar_mensagem"][0]
assert "📂 *D4* — vou guardar em Processos › FAMÍLIA › Ana Souza Lima" in txt and "NÃO PASTA D4" in txt, txt
print("OK — aviso de documento de cliente leva o código D e o destino dos arquivos")
