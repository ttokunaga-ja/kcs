"""ソース内の base64 リテラルを総当りで展開し、kcs 残存を探す。

圧縮/符号化されたデータの中身はテキスト全域置換にも `git grep` にも
届かない。改名の見落としがそこに隠れる。
"""
import base64, re, zlib, sys
from pathlib import Path

found = 0
for path in sorted(Path("eval").glob("persona_v2_*.py")):
    source = path.read_text(encoding="utf-8")
    # 64 文字以上の base64 らしき文字列リテラルを候補にする
    for literal in re.findall(r'"([A-Za-z0-9+/=]{64,})"', source):
        try:
            raw = base64.b64decode(literal.encode("ascii"), validate=True)
        except Exception:
            continue
        for decoded in (raw,):
            # zlib かもしれないので両方試す
            candidates = [decoded]
            try:
                candidates.append(zlib.decompress(decoded))
            except Exception:
                pass
            for blob in candidates:
                try:
                    text = blob.decode("utf-8")
                except Exception:
                    continue
                if "kcs" in text.lower():
                    n = text.lower().count("kcs")
                    print(f"[HIT] {path.name}: base64 literal ({len(literal)} chars) -> {n} 個の kcs")
                    for mo in list(re.finditer(r'.{0,30}[Kk][Cc][Ss].{0,30}', text))[:3]:
                        print(f"       {mo.group(0)!r}")
                    found += 1
print(f"\n埋め込みデータ内の kcs 残存: {found} 箇所")
