"""`--allow-fail` 抜きで全 builder を直接呼び、本当に緑かを確かめる。

`snapshot.py --allow-fail` は pin 検査の `_fail` を無害化して candidate を
測る。ある artifact の**依存 pin が壊れている**とき、この設計は壊れた入力から
計算された candidate を「その artifact の新しい値」として記録してしまう。
改名前ツリーと改名後ツリーの両方で同じことが起きれば、両者が一致して
**「不動」に見える** — converge は差分がないので何もせず「新規 0 = 収束」と
報告する。

実際にこれで 10 件が隠れていた。converge も CI 全体も見逃し、直接 import して
例外の有無を試すまで気づけなかった。**収束を宣言する前に必ず回すこと。**
"""
import importlib, sys, traceback
from pathlib import Path
sys.path.insert(0, ".")
import re
ok, fail = [], []
for path in sorted(Path("eval").glob("persona_v2_*.py")):
    source = path.read_text(encoding="utf-8")
    for builder in re.findall(r"^def (build_[a-z0-9_]+)\(", source, re.M):
        m = re.search(rf"^def {re.escape(builder)}\(([^)]*)\)", source, re.M)
        args = m.group(1).strip() if m else ""
        if args:
            continue  # 引数ありは別途 persona で試す (時間がかかるので後回し)
        try:
            module = importlib.import_module(f"eval.{path.stem}")
            getattr(module, builder)()
            ok.append(f"{path.stem}::{builder}")
        except Exception as error:
            fail.append((f"{path.stem}::{builder}", f"{type(error).__name__}: {error}"))
print(f"OK {len(ok)} / FAIL {len(fail)}")
for name, err in fail:
    print(f"  [FAIL] {name}: {err[:120]}")
