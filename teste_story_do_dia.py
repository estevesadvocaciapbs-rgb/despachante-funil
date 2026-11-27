"""Testes offline do story do dia. Rodar: python teste_story_do_dia.py"""
from datetime import date, datetime, timedelta

import story_do_dia as s

assert s.periodo(datetime(2026, 11, 30, 7, 30)) == "manha"
assert s.periodo(datetime(2026, 11, 30, 14, 0)) == "tarde"
assert s.periodo(datetime(2026, 11, 30, 19, 0)) == "noite"
# rotação: em len(banco) dias seguidos cada ideia aparece uma vez
for banco, per in ((s.MANHA, "manha"), (s.TARDE, "tarde"), (s.NOITE, "noite")):
    dias = [date(2026, 12, 1) + timedelta(n) for n in range(60)]
    uteis = [d for d in dias if d.weekday() < 5 and (d.month, d.day) not in s.DATAS][:len(banco) * 3]
    vistas = {s.ideia(d, per) for d in uteis}
    assert vistas <= set(banco)
    seguidos = [s.ideia(date(2026, 12, 1) + timedelta(n), per) for n in range(len(banco))]
    if per != "manha":
        assert len(set(seguidos)) == len(banco) - sum((d.month, d.day) in s.DATAS for d in
                                                      [date(2026, 12, 1) + timedelta(n) for n in range(len(banco))])
assert s.ideia(date(2026, 11, 28), "manha") in s.FIM_DE_SEMANA  # sábado
assert s.ideia(date(2026, 12, 24), "noite") == s.DATAS[(12, 24)]
t = s.texto(date(2026, 11, 30), "tarde")
assert t.startswith("📱 *Story da tarde*") and "Sticker:" in t and "Texto na tela:" in t
for banco in (s.MANHA, s.TARDE, s.NOITE, s.FIM_DE_SEMANA, list(s.DATAS.values())):
    for g, tela, st in banco:
        assert g and tela and st and "—" not in g + tela + st
print("ok story do dia")
