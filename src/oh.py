"""Parser minimo di OSM opening_hours.

Copre i formati più comuni ("24/7", "Mo-Fr 08:00-20:00; Sa 09:00-13:00",
orari oltre la mezzanotte, "off"). Le regole con mesi, settimane o festività
vengono ignorate; se non resta nulla di leggibile restituisce None.
Risultato: lista di 7 liste (lun..dom) di intervalli [inizio, fine] in minuti,
dove fine può superare 1440 (chiusura dopo mezzanotte).
"""
import re

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)"
_SEL = re.compile(rf"^\s*({_DAY}(?:\s*-\s*{_DAY})?(?:\s*,\s*{_DAY}(?:\s*-\s*{_DAY})?)*)\b\s*(.*)$")
_TIME = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})(\+)?")
_SPLIT = re.compile(rf"(?<=\d)\s*,\s*(?={_DAY}\b)")


def _days(sel):
    out = set()
    for part in re.split(r"\s*,\s*", sel):
        if "-" in part:
            a, b = [s.strip() for s in part.split("-")]
            if a in DAYS and b in DAYS:
                i, j = DAYS.index(a), DAYS.index(b)
                out.update(range(i, j + 1) if i <= j else list(range(i, 7)) + list(range(0, j + 1)))
        elif part in DAYS:
            out.add(DAYS.index(part))
    return out


def parse(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if s in ("24/7", "Mo-Su 00:00-24:00", "00:00-24:00"):
        return [[[0, 1440]] for _ in range(7)]
    week = [None] * 7
    rules = [r for chunk in s.split(";") for r in _SPLIT.split(chunk)]
    for rule in rules:
        rule = rule.strip()
        if not rule or re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|week)\b", rule):
            continue
        m = _SEL.match(rule)
        days, rest = (_days(m.group(1)), m.group(2)) if m else (set(range(7)), rule)
        if not days:
            continue  # solo PH/SH
        if re.match(r"^(off|closed)\b", rest.strip(), re.I):
            for d in days:
                week[d] = []
            continue
        ivs = []
        for h1, m1, h2, m2, plus in _TIME.findall(rest):
            a, b = int(h1) * 60 + int(m1), int(h2) * 60 + int(m2)
            if b <= a:
                b += 1440
            if plus:
                b = max(b, a + 240)  # "aperto fino a tardi": almeno 4 ore stimate
            ivs.append([a, b])
        if not ivs and rest.strip().lower() in ("24/7", "open"):
            ivs = [[0, 1440]]
        if ivs:
            for d in days:
                week[d] = ivs  # in OSM una regola successiva sovrascrive la precedente
    if all(w is None for w in week):
        return None
    return [w or [] for w in week]


def summary(week):
    """-> (chiusura_max in minuti o None, dopo_mezzanotte, h24)."""
    if week is None:
        return None, False, False
    h24 = all(any(a <= 0 and b >= 1440 for a, b in d) for d in week)
    # un intervallo 00:00-xx il giorno dopo un 'fino a 24:00' è continuità: conta come dopo mezzanotte
    ends = []
    for i, d in enumerate(week):
        for a, b in d:
            e = b
            if b == 1440:
                nxt = week[(i + 1) % 7]
                cont = [bb for aa, bb in nxt if aa == 0]
                if cont:
                    e = 1440 + max(cont)
            ends.append(e)
    if not ends:
        return None, False, False
    cmax = 1440 * 2 if h24 else max(ends)
    return cmax, h24 or cmax > 1440, h24


def fmt(minutes):
    if minutes is None:
        return ""
    if minutes >= 2880:
        return "24h"
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"
