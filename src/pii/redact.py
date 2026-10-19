"""Turn extracted entities into masked text with numbered placeholders, and back."""
import re

PLACEHOLDER = re.compile(r"\[[A-Z]+_\d+\]")


def _occurrences(text: str, value: str):
    # Boundary lookarounds stop "Max" matching inside "Maximilian" or "12" inside "123".
    pat = r"(?<!\w)" + re.escape(value) + r"(?!\w)"
    return [(m.start(), m.end()) for m in re.finditer(pat, text)]


def mask(text: str, entities: list[dict]) -> tuple[str, dict[str, str]]:
    """Replace entity values with [LABEL_n]. Returns (masked_text, placeholder -> original).

    Longest values win overlaps; the same (label, value) always gets the same placeholder,
    numbered in order of first appearance in the text.
    """
    pairs = {(e["label"], e["text"]) for e in entities if e.get("text")}
    taken: list[tuple[int, int, str, str]] = []  # start, end, label, value
    for label, value in sorted(pairs, key=lambda p: -len(p[1])):
        for s, e in _occurrences(text, value):
            if all(e <= ts or s >= te for ts, te, _, _ in taken):
                taken.append((s, e, label, value))
    taken.sort()

    ids: dict[tuple[str, str], str] = {}
    counts: dict[str, int] = {}
    mapping: dict[str, str] = {}
    out, pos = [], 0
    for s, e, label, value in taken:
        if (label, value) not in ids:
            counts[label] = counts.get(label, 0) + 1
            ids[(label, value)] = f"[{label}_{counts[label]}]"
            mapping[ids[(label, value)]] = value
        out += [text[pos:s], ids[(label, value)]]
        pos = e
    out.append(text[pos:])
    return "".join(out), mapping


def rehydrate(text: str, mapping: dict[str, str]) -> str:
    """Put original values back; placeholders not in the mapping are left untouched."""
    return PLACEHOLDER.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
