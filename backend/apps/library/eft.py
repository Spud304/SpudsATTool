"""EFT fit text parser. Pure: no Django, no name resolution (see services.resolve_items)."""

import re
from dataclasses import dataclass, field

HEADER_RE = re.compile(r"^\[(?P<hull>[^,\]]+?)(?:,\s*(?P<name>[^\]]*?))?\s*\]$")
EMPTY_SLOT_RE = re.compile(r"^\[empty .+ slot\]$", re.IGNORECASE)
QUANTITY_RE = re.compile(r"^(?P<name>.+?)\s+x(?P<qty>\d+)$")
OFFLINE_RE = re.compile(r"\s*/offline$", re.IGNORECASE)  # the client writes /OFFLINE, Pyfa /offline
MUTATION_REF_RE = re.compile(r"^(?P<name>.+?)\s+\[(?P<ref>\d+)\]$")
MUTATION_BLOCK_RE = re.compile(r"^\[(?P<ref>\d+)\]\s+\S")

NO_HEADER = "NO_HEADER"


@dataclass(frozen=True)
class EftItem:
    line_no: int
    name: str
    charge: str | None = None
    quantity: int = 1
    offline: bool = False
    mutated: bool = False  # an abyssal (mutaplasmid-rolled) copy of `name`


@dataclass(frozen=True)
class ParsedEft:
    hull_name: str
    fit_name: str
    items: tuple[EftItem, ...]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def names(self) -> set[str]:
        out: set[str] = set()
        for item in self.items:
            out.add(item.name)
            if item.charge:
                out.add(item.charge)
        return out


def normalise(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").replace("\t", " ")
    return [line.rstrip() for line in text.split("\n")]


def parse_eft(text: str) -> ParsedEft:
    """Header `[Hull, Name]` then one item per line. Blank lines separate banks but are not trusted for slot types."""
    lines = normalise(text)
    header_idx = next((i for i, line in enumerate(lines) if line.strip()), None)
    if header_idx is None:
        return ParsedEft("", "", (), errors=(f"{NO_HEADER}: empty fit",))
    m = HEADER_RE.match(lines[header_idx].strip())
    if not m:
        return ParsedEft(
            "", "", (), errors=(f"{NO_HEADER}: first line must look like [Hull, Fit name]",)
        )
    hull = m.group("hull").strip()
    name = (m.group("name") or "").strip() or hull

    items: list[EftItem] = []
    warnings: list[str] = []
    refs: dict[str, int] = {}  # mutation reference -> index in items
    blocks: set[str] = set()  # references that have their `[n] name` block
    in_block = False
    for offset, raw in enumerate(lines[header_idx + 1 :], start=header_idx + 2):
        if not raw.strip():
            continue
        if raw[0] in " \t":
            if not in_block:  # inside a `[n]` block the mutaplasmid and attribute lines belong
                warnings.append(f"line {offset}: indented text ignored (mutation attributes?)")
            continue
        in_block = False
        line = raw.strip()
        if EMPTY_SLOT_RE.match(line):
            continue
        block = MUTATION_BLOCK_RE.match(line)
        if block:
            blocks.add(block.group("ref"))
            in_block = True
            continue
        if line.startswith("["):
            warnings.append(f"line {offset}: bracketed line ignored: {line[:60]}")
            continue
        offline = False
        line, n = OFFLINE_RE.subn("", line)
        if n:
            offline = True
        quantity = 1
        qm = QUANTITY_RE.match(line)
        if qm:
            quantity = int(qm.group("qty"))
            line = qm.group("name")
        charge: str | None = None
        if ", " in line:
            line, charge = line.split(", ", 1)
            charge = charge.strip() or None
        mutated = False
        ref = MUTATION_REF_RE.match(line.strip())
        if ref:
            line, mutated = ref.group("name"), True
            refs[ref.group("ref")] = len(items)
        items.append(
            EftItem(
                line_no=offset,
                name=line.strip(),
                charge=charge,
                quantity=quantity,
                offline=offline,
                mutated=mutated,
            )
        )
    # Only mutated modules get a `[n]`, so one counts as mutated even when its block is missing (a
    # trimmed paste); the warning says the rolled attributes are then unknown.
    for missing in sorted(set(refs) - blocks, key=int):
        item = items[refs[missing]]
        warnings.append(f"line {item.line_no}: {item.name} [{missing}] has no [{missing}] block")
    return ParsedEft(hull, name, tuple(items), warnings=tuple(warnings))
