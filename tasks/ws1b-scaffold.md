# WS1b 発注書: Rust workspace スキャフォールド (Step 1 準備)

## 目的

KCS Step 1 (kcs-core + kcs-cli) の実装土台となる Rust workspace を作る。**ビジネスロジックは実装しない** — 構造・CI・CLI 骨格のみ。

## 必読 (このリポジトリの docs/ が正本)

- `docs/09-mvp-scope.md` §3 / §3.1 — Step 1 のコマンド範囲とスコープ
- `docs/06-cli-spec.md` §1 (コマンド一覧)、§7 (exit code 0-9)、§4 (--json 規約)
- `docs/README.md` §2 (Step 計画)

## 成果物

```text
Cargo.toml                 # workspace (resolver=2)
rust-toolchain.toml        # stable
.gitignore                 # target/ 等 (既存エントリを壊さない)
crates/kcs-core/           # lib crate: 空のモジュール骨格 (cas / dag / scope) + placeholder test
crates/kcs-cli/            # bin crate "kcs": clap derive
.github/workflows/ci.yml   # fmt --check / clippy -D warnings / test (ubuntu-latest, stable)
```

## kcs-cli の骨格要件

- サブコマンド: `init` / `status` / `snapshot` (alias `commit`) / `log` / `diff` / `inspect` / `tag`
- 各コマンドは「not implemented」を stderr に出し、`docs/06-cli-spec.md` §7 の exit code 体系に沿った値で終了する
  (該当コードの選定理由をコード内コメントで §7 参照付きで記す)
- exit code は enum / const で一元定義し、kcs-core 側に置く (§7 の 0-9 全値)
- `--json` グローバルフラグの受け口だけ用意 (出力実装は不要)

## 制約

- `docs/` を変更しない。依存は clap / anyhow / thiserror 程度に留める
- unsafe 禁止。edition は 2021 以上の stable
- 過剰実装しない: CAS や DAG のロジック、ファイル IO は書かない

## 受け入れ条件 (全て通ること)

```bash
cargo build --workspace
cargo test --workspace
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

完了後、変更をこのブランチ (`ws1-scaffold`) にコミットすること (メッセージは英語可)。
