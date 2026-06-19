"""Casamento de expressoes cron (5 campos) com um datetime, em Python puro.

Campos, na ordem: minuto hora dia-do-mes mes dia-da-semana.
Suporta: '*', listas 'a,b,c', faixas 'a-b', passos '*/n' e 'a-b/n'.
Dia-da-semana: 0-6 (0 = domingo); 7 tambem conta como domingo.

Regra do cron para dia: se dia-do-mes E dia-da-semana estiverem ambos
restritos (nenhum '*'), casa se QUALQUER um casar; caso contrario, é E logico.
"""

from datetime import timedelta

# (minimo, maximo) de cada campo, na ordem acima
_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _parse_field(field, lo, hi):
    """Devolve (conjunto_de_valores, era_estrela) para um campo cron."""
    is_star = field.strip() == "*"
    values = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
        else:
            base = part
        if base in ("*", ""):
            start, end = lo, hi
        elif "-" in base:
            a, b = base.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        for v in range(start, end + 1, step):
            if lo <= v <= hi:
                values.add(v)
    return values, is_star


class CronExpr:
    """Uma expressao cron compilada, com `.matches(datetime)`."""

    __slots__ = ("expr", "fields", "stars")

    def __init__(self, expr):
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(
                "cron precisa de 5 campos (min hora dia mes dia-semana): %r" % expr
            )
        self.expr = expr
        self.fields = []
        self.stars = []
        for raw, (lo, hi) in zip(parts, _BOUNDS):
            vals, star = _parse_field(raw, lo, hi)
            if not vals:
                raise ValueError("campo cron invalido: %r em %r" % (raw, expr))
            self.fields.append(vals)
            self.stars.append(star)

    def matches(self, dt):
        minute, hour, dom, month, dow = self.fields
        if dt.minute not in minute:
            return False
        if dt.hour not in hour:
            return False
        if dt.month not in month:
            return False
        # python: seg=0..dom=6  ->  cron: dom=0..sab=6
        cron_dow = (dt.weekday() + 1) % 7
        dow_set = dow | ({0} if 7 in dow else set())
        day_dom = dt.day in dom
        day_dow = cron_dow in dow_set
        dom_star = self.stars[2]
        dow_star = self.stars[4]
        if not dom_star and not dow_star:
            return day_dom or day_dow
        if not dom_star:
            return day_dom
        if not dow_star:
            return day_dow
        return True

    def next_after(self, dt, horizon_days=366):
        """Proximo horario que casa, estritamente depois de `dt` (ou None)."""
        t = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        end = t + timedelta(days=horizon_days)
        while t <= end:
            if self.matches(t):
                return t
            t += timedelta(minutes=1)
        return None

    def prev_at_or_before(self, dt, horizon_days=366):
        """Ultimo horario que casa, em `dt` ou antes (ou None)."""
        t = dt.replace(second=0, microsecond=0)
        end = t - timedelta(days=horizon_days)
        while t >= end:
            if self.matches(t):
                return t
            t -= timedelta(minutes=1)
        return None

    def __repr__(self):
        return "<CronExpr %r>" % self.expr
