# utils/edtf_parser.py
"""
Parsing dates EDTF avec dérivation date_start/date_end

IMPORTANT: Ce parser ne valide PAS la cohérence calendaire.
Validation déléguée à validator.py (strict_mode).

Modificateurs EDTF (~, ?) sont préservés via date_precision:
- "1942~"  → precision="circa"
- "1942?"  → precision="uncertain"
- "1942"   → precision="year"

Les intervalles approximatifs (ex: "1942~/1945~") sont traités
comme intervalles standards. Validator signalera un warning.
"""

from typing import Optional, Tuple
import re
import calendar


class EDTFParser:
    """Parse dates EDTF et dérive dates normalisées"""

    @staticmethod
    def parse(edtf_string: str) -> Tuple[Optional[str], Optional[str], str]:
        """
        Parse une date EDTF et retourne (date_start, date_end, precision)

        precision: day, month, year, interval, circa, uncertain, before, after, unknown
        """
        if not edtf_string or edtf_string == "../..":
            return None, None, "unknown"

        edtf = edtf_string.strip()

        # Bornes ouvertes
        if edtf.startswith("../"):
            date_end = EDTFParser._normalize_single_date(edtf[3:])
            return None, date_end, "before"

        if edtf.endswith("/.."):
            date_start = EDTFParser._normalize_single_date(edtf[:-3])
            return date_start, None, "after"

        # Intervalle fermé
        if '/' in edtf:
            parts = edtf.split('/')
            date_start = EDTFParser._normalize_single_date(parts[0])
            date_end = EDTFParser._normalize_single_date(parts[1])
            return date_start, date_end, "interval"

        # Date approximative
        if edtf.endswith('~'):
            base = edtf[:-1]
            date_start = EDTFParser._normalize_single_date(base, start=True)
            date_end = EDTFParser._normalize_single_date(base, start=False)
            return date_start, date_end, "circa"

        # Date incertaine
        if edtf.endswith('?'):
            base = edtf[:-1]
            date_start = EDTFParser._normalize_single_date(base, start=True)
            date_end = EDTFParser._normalize_single_date(base, start=False)
            return date_start, date_end, "uncertain"

        # Date exacte
        date_start = EDTFParser._normalize_single_date(edtf, start=True)
        date_end = EDTFParser._normalize_single_date(edtf, start=False)

        # Déterminer précision
        if re.match(r'^\d{4}-\d{2}-\d{2}$', edtf):
            precision = "day"
        elif re.match(r'^\d{4}-\d{2}$', edtf):
            precision = "month"
        elif re.match(r'^\d{4}$', edtf):
            precision = "year"
        else:
            precision = "unknown"

        return date_start, date_end, precision

    @staticmethod
    def _normalize_single_date(date_str: str, start: bool = True) -> Optional[str]:
        """Normalise une date partielle en date complète"""
        if not date_str:
            return None

        date_str = date_str.rstrip('~?')

        # Année seule
        if re.match(r'^\d{4}$', date_str):
            return f"{date_str}-01-01" if start else f"{date_str}-12-31"

        # Année-Mois
        if re.match(r'^\d{4}-\d{2}$', date_str):
            year, month = date_str.split('-')
            if start:
                return f"{date_str}-01"
            else:
                last_day = calendar.monthrange(int(year), int(month))[1]
                return f"{date_str}-{last_day:02d}"

        # Année-Mois-Jour
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        return None