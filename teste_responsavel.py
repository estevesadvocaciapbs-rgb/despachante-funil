"""Testes da atribuição de conversa à advogada (dados fictícios; caso de 04/11)."""
import responsavel_conversa as rc


class Z:
    def __init__(self):
        self.env = []

    def chamar(self, f, **a):
        self.env.append((f, a))
        if f == "buscar_contatos":
            return {"contatos": [
                {"id": "c1", "name": "Ana Cliente Fernanda ", "phone": "5500000000001"},
                {"id": "c2", "name": "Fernanda Teste", "phone": "5500000000002"},
                {"id": "c3", "name": "Fernanda Mesquita | Advogada", "phone": "5594991742534"},
                {"id": "c4", "name": "Dra. Fernanda Outra", "phone": "5500000000004"},
                {"id": "c5", "name": "Bruno Criminal Fernanda", "phone": "5500000000005"}]}
        if f == "listar_contatos":
            return {"contatos": [{"id": "c6", "name": "Carla", "phone": "5500000000006"}]}
        if f == "listar_tarefas":
            return {"tarefas": [{"contatoId": "c7", "completedAt": None}, {"contatoId": "c8", "completedAt": "x"}]}
        if f == "listar_conversas_por_contato":
            st = "CLOSED" if a["contatoId"] == "c5" else "OPEN"
            return {"conversas": [{"id": "conv-" + a["contatoId"], "status": st}]}
        return {}


rc._feitas.clear(); rc._ultima[0] = 0.0
z, cont, logs = Z(), {}, []
rc.rodada(z, cont, logs.append, agora=10_000)
feitas = sorted(a["conversaId"] for f, a in z.env if f == "atribuir_conversa")
assert feitas == ["conv-c1", "conv-c6", "conv-c7"], feitas
assert all(a["responsavelId"] == "claude-usuario-3" for f, a in z.env if f == "atribuir_conversa")
assert "Ana" not in " ".join(logs)
# dentro de 30 minutos não roda de novo; depois roda mas não repete o que já fez
z2 = Z(); rc.rodada(z2, {}, logs.append, agora=10_000 + 60); assert z2.env == []
z3 = Z(); rc.rodada(z3, {}, logs.append, agora=10_000 + 1900)
assert not [a for f, a in z3.env if f == "atribuir_conversa"], z3.env
# simulação não atribui
rc._feitas.clear(); rc._ultima[0] = 0.0
z4 = Z(); rc.rodada(z4, {}, logs.append, dry_run=True, agora=10_000)
assert not [a for f, a in z4.env if f == "atribuir_conversa"]
print("OK — conversa de cliente da Dra. Fernanda vai para o nome dela (pedido de 04/11)")
