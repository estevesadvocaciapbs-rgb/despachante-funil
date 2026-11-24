"""Os arquivos .yml do GitHub Actions precisam ser YAML válido (24/11: um dois-pontos dentro de um echo quebrou o
despachante.yml e o plantão ficou parado ~30 min, porque o 'Chamar o próximo plantão' não achava o workflow).
Rodar: python teste_workflows.py"""
import glob

import yaml

for f in glob.glob(".github/workflows/*.yml"):
    d = yaml.safe_load(open(f, encoding="utf-8"))
    assert isinstance(d, dict) and "jobs" in d, f
print("ok — workflows válidos")
