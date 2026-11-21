"""Fonte E: Google Places. DISATTIVATA.

Vincolo di Giovanni (21/11/2026): costo zero. La v1 usa solo fonti open.
Il modulo resta come segnaposto: se un giorno si attiva, va usato solo sui
candidati con score >= 30, con cache su disco e rispettando i ToS Google.
"""


def run(*_, **__):
    print("  Google Places: disattivato (vincolo costo zero)")
    return None
