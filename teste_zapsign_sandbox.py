"""Teste de ponta a ponta no AMBIENTE DE TESTE do ZapSign (sem validade jurídica), com dados fictícios.
Roda pelo GitHub (workflow teste-zapsign.yml), que tem o segredo ZAPSIGN_TOKEN. Não imprime link nem dado."""
import os
import zapsign as z

assert os.environ.get("ZAPSIGN_AMBIENTE", "sandbox") == "sandbox", "este teste só roda no sandbox"
assert z.ativo(), "sem ZAPSIGN_TOKEN"
CLIENTE = {"NOME_COMPLETO": "Fulano de Teste", "NACIONALIDADE": "brasileiro", "ESTADO_CIVIL": "solteiro",
           "PROFISSAO": "operador de máquinas", "RG": "0000000", "ORGAO_EMISSOR": "SSP/PA", "CPF": "000.000.000-00",
           "ENDERECO_COMPLETO": "Rua Fictícia, 1, Bairro Teste", "CIDADE": "Parauapebas", "UF": "PA",
           "CEP": "68515-000", "PARTE_CONTRARIA": "Empresa Fictícia Ltda."}
r = z.criar_kit(CLIENTE, "5594900000001", "teste-sandbox")
print("documento criado no sandbox:", r["doc"], "| link de assinatura:", "sim" if r["link"].startswith("https://") else "NÃO")
s = z.situacao(r["doc"])
print("situação:", s["status"])
assert s["status"] == "pending", s["status"]
print("ok — ZapSign sandbox de ponta a ponta")
