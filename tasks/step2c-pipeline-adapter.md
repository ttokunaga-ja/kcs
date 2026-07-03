# Step2c 発注書: kcs-pipeline + kcs-adapter 本体実装 (Step 2)

## 目的

KCS Step 2 の本体実装。**契約テスト仕様 `tasks/step2a-contract-tests.md` (r2) の P0 52 件を green にする**ことが完了条件。

## 前提 (main に揃っている)

- Step 1 実装済み: kcs-core (CAS / DAG / lock / schema validation) + kcs-cli
- スキャフォールド: `crates/kcs-pipeline` / `crates/kcs-adapter` (型定義 + todo!() スタブ)
- 契約テスト仕様: `tasks/step2a-contract-tests.md` — ベクタは実計算済み・クロスレビューで再計算一致確認済み。**ベクタ期待値の変更禁止**
- spec 追記済み (2026-07-03): unit_key 正準規則 (04 §2)、page fingerprint MVP アルゴリズム + prepared 決定性 (04 §2.1)、prompt_template_hash 正規化 (03 §5.1)、.kcsignore 文法 (03 §11.1)、`kcs index --online/--offline` (06 §1)、版付きモデル名解決の pin 規約 (07 §6)

## 実装範囲 (正本: docs/09-mvp-scope.md §3.1 の Step 2 行)

1. `kcs index` (preview / approve / yes / online / offline、初回承認、非対話 exit 2、承認記録 + approval_method)
2. `.kcsignore` (03 §11.1 文法) + secrets Tier A/B + quarantine (10 §1.1)
3. preview のコスト概算・budget 超過警告 (10 §1 / 06 §2)
4. scan → prepare → markdownize パイプライン: unit model (04 §2)、unit_mapping (04 §2.2)、full + incremental (04 §3.1 発動条件 AND 5)、受け入れ検査 V1-V6 (04 §3.2、違反は KCS-E-ADAPTER-CONTRACT-001 + full fallback)
5. 同梱 deterministic Adapter (07 §2.1: text/Markdown/コード passthrough + PDF text layer 抽出) によるベースライン index
6. `mistral_ocr_markdownize` Adapter (07 §5.2/§6): 版付きモデル名の起動時解決 + pin、表 inline、image object 保存 (03 §2) + `kcs://<scope_id>/object/image/<hash>` URI **生成** (解決は Step 3)、bbox/confidence は unit metadata
7. batch / retry / resume / budget guardrail (04 §5: task 状態機械、エラー種別別 retry budget、二層 cap = device+folder の min AND、cost ledger、--override-budget、冪等性)
8. network opt-in (07 §3: 単位 = scope × adapter、寿命 = 永続、revoke、未承認では online task 不発行・pending 残留)
9. index 成功完了時の auto snapshot (05 §8.1、commit_type=auto、tree 不変なら no-op — CT2-INDEX)
10. tools.toml / tool-lock.json の schema validation、観測ログへの記録

## 実装手順

1. step2a の P0 52 を Rust テストに落とす (モック Adapter で API 非依存に)。ベクタ (tool_profile_hash 等) は fixture として一致 assert
2. 実装を green に。**実 Mistral API を叩くテストは書かない** — Adapter trait のモックで契約検証し、実 API 検証は `experiments/ocr-verification` (完了済み) が担う。HTTP 層は env `MISTRAL_API_KEY` 前提の薄い client (依存は最小: ureq (rustls) 等の軽量クレートを推奨、reqwest 可)

## spec 未定義部の暫定判断 (step2a §C-6〜C-11。この通り実装し `tasks/ws1c-decisions.md` に追記)

```text
C-6  incremental 連続カウンタ    → file_id 単位で数え、full 実行 (fallback 含む) でリセット
C-7  task_id / run_id            → ULID (kcs-core の実装を再利用)。prefix "task_" / "run_"
C-8  cost-ledger schema          → 最小 schema (month TEXT UTC, scope_id, adapter_kind, usd REAL) を
                                   実装者が確定し decisions に記録。月境界は UTC
C-9  quarantine 解除の記録       → 承認記録 (approval_method 付き) と同じ場所・同形式で 1 行追記
C-10 scanned PDF (text layer 無) → baseline では unit を作らず file を pending (AI 強化待ち) とする。
                                   kcs status に pending として表示
C-11 image placeholder 置換      → Mistral 応答の images[] と Markdown 内 placeholder を出現順で対応付け、
                                   ![...](kcs://<scope_id>/object/image/<image_hash>) に置換
```

## 制約

- LOC 目安: テスト除き 3,500-5,000 (09 §3)。超えそうなら削る相談を先に
- `docs/` 変更禁止。spec の矛盾・実装不能は `tasks/ws1c-decisions.md` に記録して継続
- API キー・秘匿情報をコード/テスト/fixture に書かない。ネットワークはモックのみ (CI で外部通信ゼロ)
- 既存 kcs-core の変更は最小限 (公開 API 追加は可、既存契約テストを壊さない)
- unsafe 禁止

## 受け入れ条件

```bash
cargo test --workspace          # step2a P0 52 全 green + Step 1 の既存 33 テスト回帰なし
cargo clippy --all-targets -- -D warnings
cargo fmt --check
```

ブランチ `step2c-impl` (main から分岐) にコミットすること。完了後、発注側が多エンジン監査 (Step 1 と同様の 4 エンジン + 焦点再監査) を実施する。
