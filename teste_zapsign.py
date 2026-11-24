"""Testes da ligação com o ZapSign, sem internet (resposta falsa). Dados fictícios. Rodar: python teste_zapsign.py"""
import io
import json
import os
from datetime import date

os.environ["ZAPSIGN_TOKEN"] = "teste"
os.environ.pop("ZAPSIGN_AMBIENTE", None)
os.environ.pop("ZAPSIGN_MODELO_RECLAMANTE", None)
import zapsign as z  # noqa: E402

CLIENTE = {"NOME_COMPLETO": "Fulano de Teste", "NACIONALIDADE": "brasileiro", "ESTADO_CIVIL": "solteiro",
           "PROFISSAO": "operador de máquinas", "RG": "0000000", "ORGAO_EMISSOR": "SSP/PA", "CPF": "000.000.000-00",
           "ENDERECO_COMPLETO": "Rua Fictícia, 1, Bairro Teste", "CIDADE": "Parauapebas", "UF": "PA",
           "CEP": "68515-000", "PARTE_CONTRARIA": "Empresa Fictícia Ltda."}
pedidos = []


def abrir_falso(resposta):
    def abrir(req, timeout=60):
        pedidos.append(req)
        return io.BytesIO(json.dumps(resposta).encode())
    return abrir


r = z.criar_kit(CLIENTE, "5594900000001", "lead-1", hoje=date(2026, 11, 24),
                abrir=abrir_falso({"token": "d1", "signers": [{"sign_url": "https://x/verificar/s1"}]}))
assert r == {"doc": "d1", "link": "https://x/verificar/s1"}
req = pedidos[-1]
corpo = json.loads(req.data)
assert req.full_url == "https://sandbox.api.zapsign.com.br/api/v1/models/create-doc/" and req.get_method() == "POST"
assert req.headers["Authorization"] == "Bearer teste"
assert corpo["template_id"] == z.MODELO_TESTE and corpo["external_id"] == "lead-1"
assert corpo["send_automatic_whatsapp"] is False and corpo["send_automatic_email"] is False
assert corpo["signer_phone_number"] == "94900000001" and corpo["signer_name"] == "Fulano de Teste"
d = {x["de"]: x["para"] for x in corpo["data"]}
assert d["{{QTD_SM_TUTELA}}"] == "1" and d["{{DATA}}"] == "24 de novembro de 2026"
assert d["{{TELEFONE_CLIENTE}}"] == "(94) 900000001" and d["{{EMAIL_CLIENTE}}"] == "não informado"
assert len(d) == 16, sorted(d)
# faltando campo: não chama o ZapSign
n = len(pedidos)
try:
    z.criar_kit(dict(CLIENTE, CPF=""), "5594900000001", "lead-2", abrir=abrir_falso({}))
    raise AssertionError("deveria recusar")
except z.ErroZapSign as e:
    assert "CPF" in str(e) and len(pedidos) == n
# resposta estranha: erro, não link vazio
try:
    z.criar_kit(CLIENTE, "5594900000001", "lead-3", abrir=abrir_falso({"token": "d2", "signers": []}))
    raise AssertionError("deveria recusar")
except z.ErroZapSign:
    pass
# produção usa outro endereço e o modelo do segredo
os.environ.update(ZAPSIGN_AMBIENTE="producao", ZAPSIGN_MODELO_RECLAMANTE="modelo-real")
z.criar_kit(CLIENTE, "94900000001", "lead-4", abrir=abrir_falso({"token": "d3", "signers": [{"sign_url": "u"}]}))
assert pedidos[-1].full_url.startswith("https://api.zapsign.com.br/") and json.loads(pedidos[-1].data)["template_id"] == "modelo-real"
os.environ.pop("ZAPSIGN_AMBIENTE"), os.environ.pop("ZAPSIGN_MODELO_RECLAMANTE")
# situação do documento
s = z.situacao("d1", abrir=abrir_falso({"status": "signed", "signed_file": "https://x/assinado.pdf"}))
assert s == {"status": "signed", "pdf": "https://x/assinado.pdf"} and pedidos[-1].full_url.endswith("/docs/d1/")
print("ok — zapsign")
