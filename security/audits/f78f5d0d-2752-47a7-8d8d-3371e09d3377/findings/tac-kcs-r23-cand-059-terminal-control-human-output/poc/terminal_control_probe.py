#!/usr/bin/env python3
"""Non-emitting probe for terminal-control byte handling.

The vulnerable KCS human-output branch would pass the string bytes directly to
stdout. This probe intentionally does not do that. It prints only hexadecimal
and JSON-escaped representations so the operator's terminal never receives the
raw control sequence.
"""

import json


def spaced_hex(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def main() -> int:
    payload = b"SAFE\x1b]0;synthetic-title\x07END"
    decoded = payload.decode("utf-8")
    json_encoded = json.dumps(decoded)

    print("[+] synthetic payload bytes:")
    print(f"    {spaced_hex(payload)}")
    print(f"[+] raw branch would contain ESC: {'yes' if 0x1B in payload else 'no'}")
    print(f"[+] raw branch would contain BEL: {'yes' if 0x07 in payload else 'no'}")
    print("[+] JSON branch:")
    print(f"    {json_encoded}")
    print(
        "[+] JSON branch contains raw ESC byte: "
        f"{'yes' if chr(0x1B) in json_encoded else 'no'}"
    )

    if chr(0x1B) in json_encoded:
        print("[-] unexpected raw ESC remained after JSON encoding")
        return 1
    print("[+] safe probe completed without emitting the raw control sequence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
