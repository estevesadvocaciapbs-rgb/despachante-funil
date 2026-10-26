"""Teste manual (só leitura), autorizado pela usuária em 26/10/2026: a Za.Ia deixa baixar o arquivo
de uma conversa usando o token da API? Se deixar, o despachante pode salvar os arquivos dos clientes
na pasta do Drive sem a integração do painel.

Pega a mídia mais recente do privado da Dra. Danielle com o escritório e tenta baixar de algumas formas.
O log mostra só o código HTTP, o tipo e o tamanho — nunca o conteúdo, o link nem o token.
"""
import os
import urllib.error
import urllib.request

import despachante as d

zaia = d.MCP(d.ZAIA_URL, os.environ.get("ZAIA_TOKEN"), "Za.Ia")
conv = (zaia.chamar("buscar_conversa_por_telefone", telefone="5594992048054") or {}).get("conversa") or {}
msgs = (zaia.chamar("ler_conversa", conversaId=conv["id"]) or {}).get("messages", [])
com_midia = [m for m in sorted(msgs, key=lambda m: m["createdAt"], reverse=True) if m.get("mediaUrl")]
print(f"mensagens com mídia: {len(com_midia)}")
for m in com_midia[:2]:
    caminho = m["mediaUrl"]
    print(f"tipo da mensagem: {m.get('contentType')} · rota: /{caminho.split('/')[1]}/{caminho.split('/')[2]}/…")
    tentativas = [
        ("app + Authorization Bearer", "https://app.zaials.com.br" + caminho, {"Authorization": f"Bearer {zaia.token}"}),
        ("app + x-api-key", "https://app.zaials.com.br" + caminho, {"x-api-key": zaia.token}),
        ("mcp + Authorization Bearer", "https://mcp.zaials.com.br" + caminho, {"Authorization": f"Bearer {zaia.token}"}),
    ]
    for nome, url, cab in tentativas:
        cab = dict(cab, **{"User-Agent": "despachante-funil/2.0"})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=30) as r:
                corpo = r.read()
                print(f"  {nome}: HTTP {r.status} · {r.headers.get('Content-Type')} · {len(corpo)} bytes")
        except urllib.error.HTTPError as e:
            print(f"  {nome}: HTTP {e.code} · {e.headers.get('Content-Type')}")
        except Exception as e:
            print(f"  {nome}: falhou ({type(e).__name__})")
