"""Telefone do cadastro do EasyJur → número de WhatsApp como a Za.Ia guarda (55 + DDD + 9 dígitos).

Caso de 27/10/2026: o celular estava cadastrado no formato antigo, sem o 9 da frente ("(81) 9211-5499"),
e a Za.Ia não achava a conversa. Celular de 8 dígitos (começa com 6, 7, 8 ou 9) ganha o 9; fixo fica como está.
"""

import re

CAMPOS = ("celular", "celular2", "telefone", "telefone2")


def whatsapp(valor):
    dig = re.sub(r"\D", "", str(valor or "")).lstrip("0")
    if len(dig) in (10, 11):
        dig = "55" + dig
    if len(dig) not in (12, 13) or not dig.startswith("55"):
        return None
    if len(dig) == 12 and dig[4] in "6789":  # celular antigo, sem o 9
        dig = dig[:4] + "9" + dig[4:]
    return dig


def do_cadastro(pessoa):
    """Primeiro número válido do cadastro (celular antes de telefone fixo), ou None."""
    for campo in CAMPOS:
        tel = whatsapp((pessoa or {}).get(campo))
        if tel:
            return tel
    return None
