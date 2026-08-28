import re

# Les créneaux sont stockés en minutes depuis 00:00 ; le contrat API parle
# toujours de "HH:MM" — cette conversion se fait uniquement à cette
# frontière.
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def hhmm_to_minutes(hhmm: str) -> int:
    match = _HHMM_RE.match(hhmm)
    if not match:
        raise ValueError(f'Format d\'heure invalide : "{hhmm}" (attendu "HH:MM").')
    return int(match.group(1)) * 60 + int(match.group(2))


def minutes_to_hhmm(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def is_valid_hhmm(value: str) -> bool:
    return bool(_HHMM_RE.match(value))
