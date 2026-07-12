#!/usr/bin/env python3
"""Offline model of KCS OCR page-index mapping for KCS-R23-CAND-051."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    index: int
    markdown: str


@dataclass(frozen=True)
class Hint:
    unit_key: str
    order: int


def vulnerable_map(pages: list[Page], hints: list[Hint]) -> list[tuple[str, str]]:
    pages_by_index: dict[int, Page] = {}
    for page in pages:
        pages_by_index[page.index] = page

    units: list[tuple[str, str]] = []
    for hint in hints:
        page = pages_by_index.get(hint.order)
        if page is None and hint.order < len(pages):
            page = pages[hint.order]
        if page is not None:
            units.append((hint.unit_key, page.markdown))
    return units


def strict_key_shape_validation(
    units: list[tuple[str, str]], expected_unit_keys: set[str]
) -> bool:
    actual_unit_keys = {unit_key for unit_key, _ in units}
    return actual_unit_keys == expected_unit_keys and all(markdown for _, markdown in units)


def proposed_bijection_check(pages: list[Page], expected_len: int) -> None:
    seen: set[int] = set()
    for page in pages:
        if page.index >= expected_len:
            raise ValueError(f"page index {page.index} out of range")
        if page.index in seen:
            raise ValueError(f"duplicate page index {page.index}")
        seen.add(page.index)
    expected = set(range(expected_len))
    if seen != expected:
        missing = sorted(expected - seen)
        raise ValueError(f"missing page indices {missing}")


def markdowns(units: list[tuple[str, str]]) -> list[str]:
    return [markdown for _, markdown in units]


def main() -> None:
    hints = [Hint("page:1", 0), Hint("page:2", 1)]
    expected_keys = {hint.unit_key for hint in hints}

    attack_pages = [Page(0, "page-A"), Page(0, "page-B")]
    attack_units = vulnerable_map(attack_pages, hints)
    attack_outputs = markdowns(attack_units)
    attack_valid = strict_key_shape_validation(attack_units, expected_keys)

    control_pages = [Page(0, "page-A"), Page(1, "page-B")]
    control_outputs = markdowns(vulnerable_map(control_pages, hints))

    try:
        proposed_bijection_check(attack_pages, len(hints))
    except ValueError as err:
        proposed_rejection = str(err)
    else:
        raise AssertionError("attack pages unexpectedly passed bijection check")

    assert attack_outputs == ["page-B", "page-B"], attack_outputs
    assert attack_valid is True
    assert control_outputs == ["page-A", "page-B"], control_outputs

    print("[+] attack provider pages: [(0, 'page-A'), (0, 'page-B')]")
    print(f"[+] attack mapped outputs: {attack_outputs!r}")
    print(f"[+] strict coverage validation still passes: {attack_valid}")
    print(f"[+] unique-index control outputs: {control_outputs!r}")
    print(f"[+] proposed bijection check rejects attack: {proposed_rejection}")


if __name__ == "__main__":
    main()
