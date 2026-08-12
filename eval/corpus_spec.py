"""Kio 検索評価ハーネス — 合成コーパスと履歴シナリオの単一定義 (正本).

docs/09-mvp-scope.md §4.3 のゴールデンクエリ評価規約に対応する合成コーパスと
履歴シナリオ (編集 / リネーム / 削除) を **決定論的** に定義するモジュール。
generate_corpus.py / replay_history.py と限定的な Python oracle が本モジュールを共有し、
コーパス・履歴・ゴールデンクエリの整合を構造的に保証する (drift を防ぐ)。

設計:
  - 依存は Python3 標準ライブラリのみ (hashlib / random)。
  - 乱数はすべて hashlib 由来の固定 seed で初期化 (PYTHONHASHSEED 非依存)。
  - anchor 文書 = ゴールデンクエリが指す「意味のある固有名詞・数値付き」文書。
  - filler 文書 = 検索ノイズ / 規模を稼ぐ手続き生成文書 (クエリ対象外)。
  - scope 配置は docs/03-data-model.md §3「直下のみ」規則に従い各 scope 直下に flat 配置。

シナリオ対応 (docs/09 §4):
  - M3-1: 現行 tree 検索。anchor は不変 (編集/リネーム/削除しない)。
  - M3-2: --all-history。リネーム済み anchor (旧名で記憶) + 編集済み anchor (旧値は履歴のみ)。
  - M3-3: --include-deleted。削除済み anchor の数値を再発見。
"""

import hashlib
import random

# --- 決定論の要 (seed 固定) ---------------------------------------------------
SEED = 20260703
CORPUS_MANIFEST_NAME = "corpus-manifest.json"

# docs 09 §4.3 の「複数 scope 構成」。5-10 scope。各 scope 直下に flat 配置する。
SCOPES = [
    "research",
    "notes",
    "downloads",
    "projects-a",
    "projects-b",
    "specs",
    "journal",
]

# scope あたりの filler 文書数 (合計と anchor 数で 200-500 に収める)。
FILLER_PER_SCOPE = {
    "research": 40,
    "notes": 40,
    "downloads": 40,
    "projects-a": 39,
    "projects-b": 39,
    "specs": 38,
    "journal": 38,
}
# うち各 scope でこの本数を ASCII 英語の text-native PDF にする (残りは .md / .txt)。
FILLER_PDF_PER_SCOPE = 2


def _seed_int(*parts):
    """文字列群から安定な 64bit seed を導出 (hash randomization 非依存)."""
    digest = hashlib.sha256("::".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


# --- 語彙 (数値・固有名詞・言い換えを意図した設計) -----------------------------
CODENAMES = [
    "Falcon", "Kestrel", "Merlin", "Osprey", "Harrier", "Condor",
    "Sakura", "Hayabusa", "Tsubame", "Komodo", "Raiden", "Suzaku",
]
JA_TERMS = [
    "認証", "トークン", "レイテンシ", "スループット", "リトライ", "スナップショット",
    "埋め込み", "チャンク", "インデックス", "キャッシュ", "レプリケーション",
    "シャーディング", "再ランク", "回収率", "整合性", "冪等性", "分散トレース",
]
EN_TERMS = [
    "embedding", "latency", "throughput", "retry", "snapshot", "recall",
    "sharding", "replication", "cache", "rerank", "idempotency", "tracing",
]
UNITS = ["ms", "req/min", "QPS", "GB", "件", "秒", "%", "万円", "USD"]


def _sentence(rng):
    code = rng.choice(CODENAMES)
    ja = rng.choice(JA_TERMS)
    en = rng.choice(EN_TERMS)
    num = rng.choice([12, 27, 64, 128, 256, 420, 512, 780, 1000, 1240, 3200, 6000])
    unit = rng.choice(UNITS)
    templates = [
        f"{code} の {ja} は {num}{unit} を目標値とした。",
        f"{en} の測定では {code} が {num}{unit} を記録した。",
        f"{ja}({en}) の設定値は {num}{unit} に固定する。",
        f"The {en} of {code} settled around {num} {unit}.",
        f"{code} における {ja} の実測は {num}{unit} 前後で安定した。",
    ]
    return rng.choice(templates)


def _paragraph(rng, n_sentences):
    return " ".join(_sentence(rng) for _ in range(n_sentences))


# --- anchor 文書定義 -----------------------------------------------------------
# 各 anchor: scope, file(原名), title, sections[{slug, heading, facts[]}].
# facts は「本文の数値や用語の一部だけ覚えている」を再現できる固有情報 (verbatim 埋込)。
# role は評価上の位置づけ (m3_1_stable / m3_2_rename / m3_2_edit / m3_3_delete)。

ANCHORS = [
    # === M3-1: 現行 tree に残る安定 anchor ===
    {
        "scope": "research", "file": "embedding-benchmark.md",
        "title": "埋め込みモデル ベンチマーク 2026Q2", "role": "m3_1_stable",
        "sections": [
            {"slug": "recall", "heading": "回収率と精度",
             "facts": ["Osprey モデルの Recall@10 は 0.83、Recall@20 は 0.89 だった。",
                       "p95 レイテンシは 420ms、p99 は 610ms を記録した。"]},
            {"slug": "throughput", "heading": "スループットとメモリ",
             "facts": ["バッチ埋め込みは 3,200 チャンク/秒 を維持した。",
                       "常駐メモリは 6.4GB、次元数は 1,024 次元。"]},
        ],
    },
    {
        "scope": "research", "file": "latency-report.md",
        "title": "検索レイテンシ調査レポート", "role": "m3_1_stable",
        "sections": [
            {"slug": "tail", "heading": "テールレイテンシ",
             "facts": ["ハイブリッド検索の p95 は 780ms、p99 は 1,240ms。",
                       "20 scope 横断・10万チャンク前提で計測した。"]},
            {"slug": "cache", "heading": "キャッシュ効果",
             "facts": ["埋め込みキャッシュのヒット率は 92% だった。",
                       "キャッシュ無効時は p95 が 1,900ms へ悪化した。"]},
        ],
    },
    {
        "scope": "notes", "file": "kickoff-2026-04.md",
        "title": "Falcon キックオフ議事録 2026-04-08", "role": "m3_1_stable",
        "sections": [
            {"slug": "budget", "heading": "予算と体制",
             "facts": ["初年度予算は 480万円、専任は 3 名で合意した。",
                       "オンライン強化の月次上限は 10 USD に設定する。"]},
            {"slug": "schedule", "heading": "スケジュール",
             "facts": ["最初のマイルストーンは 5/20、ベータは 7/15 を目標。"]},
        ],
    },
    {
        "scope": "notes", "file": "retrospective-q1.md",
        "title": "Q1 ふりかえり議事録", "role": "m3_1_stable",
        "sections": [
            {"slug": "velocity", "heading": "ベロシティ",
             "facts": ["スプリント平均ベロシティは 42pt。計画比 +8% で着地した。"]},
            {"slug": "incidents", "heading": "障害とMTTR",
             "facts": ["四半期の障害は 3 件、平均復旧時間 (MTTR) は 27 分だった。"]},
        ],
    },
    {
        "scope": "downloads", "file": "vector-db-comparison.md",
        "title": "ベクトルDB 比較資料", "role": "m3_1_stable",
        "sections": [
            {"slug": "qps", "heading": "クエリ性能",
             "facts": ["Komodo エンジンは 18,000 QPS を達成した。",
                       "リコール 0.9 維持時の ef_search は 128。"]},
            {"slug": "pricing", "heading": "価格",
             "facts": ["マネージド価格は 100万ベクトルあたり 0.12 USD。"]},
        ],
    },
    {
        "scope": "projects-a", "file": "falcon-architecture.md",
        "title": "Falcon アーキテクチャ概要", "role": "m3_1_stable",
        "sections": [
            {"slug": "sharding", "heading": "シャーディング",
             "facts": ["16 シャード構成、レプリカ係数 3 で運用する。"]},
            {"slug": "auth", "heading": "認証",
             "facts": ["アクセストークンの TTL は 3,600 秒、署名は HS256。"]},
        ],
    },
    {
        "scope": "projects-a", "file": "falcon-slo.md",
        "title": "Falcon SLO 定義", "role": "m3_1_stable",
        "sections": [
            {"slug": "availability", "heading": "可用性目標",
             "facts": ["可用性 SLO は 99.95%。月間エラーバジェットは 21 分。"]},
            {"slug": "latency", "heading": "レイテンシ目標",
             "facts": ["検索 API の p95 目標は 5 秒未満 (M3-1 と整合)。"]},
        ],
    },
    {
        "scope": "projects-b", "file": "kestrel-datamodel.md",
        "title": "Kestrel データモデル", "role": "m3_1_stable",
        "sections": [
            {"slug": "schema", "heading": "スキーマ規模",
             "facts": ["現行スキーマは 42 テーブル、主要 index は 12 本。"]},
            {"slug": "retention", "heading": "保持ポリシー",
             "facts": ["監査ログの保持期間は 180 日。"]},
        ],
    },
    {
        "scope": "projects-b", "file": "kestrel-api.md",
        "title": "Kestrel API 仕様", "role": "m3_1_stable",
        "sections": [
            {"slug": "ratelimit", "heading": "レート制限",
             "facts": ["既定レート制限は 2,000 req/min、バースト 5,000。"]},
            {"slug": "pagination", "heading": "ページング",
             "facts": ["1 ページあたり 50 件、cursor 方式で返す。"]},
        ],
    },
    {
        "scope": "specs", "file": "search-ranking-spec.md",
        "title": "検索ランキング仕様", "role": "m3_1_stable",
        "sections": [
            {"slug": "rrf", "heading": "RRF 融合",
             "facts": ["FTS とベクトルの融合は RRF、定数 k=60 を用いる。"]},
            {"slug": "mmr", "heading": "MMR 多様化",
             "facts": ["再ランクの多様化は MMR、係数 λ=0.7。"]},
        ],
    },
    {
        "scope": "specs", "file": "chunking-spec.md",
        "title": "チャンク分割仕様", "role": "m3_1_stable",
        "sections": [
            {"slug": "size", "heading": "チャンクサイズ",
             "facts": ["チャンクは見出し単位、上限 6,000 文字。"]},
            {"slug": "identity", "heading": "同一性",
             "facts": ["chunk identity は raw_hash と tool_profile_hash と span で決まる。"]},
        ],
    },
    {
        "scope": "journal", "file": "reading-2026-05.md",
        "title": "論文読書メモ 2026-05", "role": "m3_1_stable",
        "sections": [
            {"slug": "hnsw", "heading": "HNSW メモ",
             "facts": ["HNSW の ef_search は 128、M は 16 が推奨。"]},
            {"slug": "rerank", "heading": "再ランクメモ",
             "facts": ["cross-encoder 再ランクは上位 100 件に適用が費用対効果が高い。"]},
        ],
    },

    # === M3-2: リネームされる anchor (旧名で記憶。--all-history) ===
    {
        "scope": "research", "file": "auth-spec.md",
        "title": "認証仕様 (旧版)", "role": "m3_2_rename",
        "sections": [
            {"slug": "api-token", "heading": "API トークン",
             "facts": ["トークン TTL は 3,600 秒、リフレッシュは 14 日。",
                       "署名アルゴリズムは HS256 を採用する。"]},
            {"slug": "scopes", "heading": "スコープ",
             "facts": ["スコープは read / write / admin の 3 種。"]},
        ],
    },
    {
        "scope": "notes", "file": "vendor-eval.md",
        "title": "ベンダー評価メモ", "role": "m3_2_rename",
        "sections": [
            {"slug": "cost", "heading": "コスト評価",
             "facts": ["ベンダー A の年間見積は 320万円 だった。"]},
            {"slug": "sla", "heading": "SLA 評価",
             "facts": ["提示 SLA は 99.9%、クレジットは 10%。"]},
        ],
    },
    {
        "scope": "downloads", "file": "rag-pipeline.md",
        "title": "RAG パイプライン資料", "role": "m3_2_rename",
        "sections": [
            {"slug": "stages", "heading": "段構成",
             "facts": ["取得は 5 段構成、再ランクに Merlin を用いる。"]},
            {"slug": "chunks", "heading": "チャンク設定",
             "facts": ["チャンクは 512 トークン、オーバーラップ 64。"]},
        ],
    },
    {
        "scope": "projects-a", "file": "falcon-migration.md",
        "title": "Falcon 移行計画", "role": "m3_2_rename",
        "sections": [
            {"slug": "window", "heading": "切替ウィンドウ",
             "facts": ["本番切替は 6/15 02:00 JST、想定停止 8 分。"]},
            {"slug": "rollback", "heading": "ロールバック",
             "facts": ["ロールバック手順は 15 分以内で完了する設計。"]},
        ],
    },
    {
        "scope": "projects-b", "file": "kestrel-security.md",
        "title": "Kestrel セキュリティ", "role": "m3_2_rename",
        "sections": [
            {"slug": "encryption", "heading": "暗号化",
             "facts": ["保存時暗号は AES-256-GCM を用いる。"]},
            {"slug": "keyrotation", "heading": "鍵ローテーション",
             "facts": ["鍵ローテーション周期は 90 日。"]},
        ],
    },
    {
        "scope": "specs", "file": "evidence-pointer-spec.md",
        "title": "Evidence Pointer 仕様 (旧名)", "role": "m3_2_rename",
        "sections": [
            {"slug": "fields", "heading": "必須フィールド",
             "facts": ["pointer は commit と raw_hash と chunk_hash と span を含む。"]},
            {"slug": "verify", "heading": "検証",
             "facts": ["verify --strict は tombstoned/not_found があれば exit 4。"]},
        ],
    },
    {
        "scope": "journal", "file": "interview-notes.md",
        "title": "ユーザーインタビュー記録", "role": "m3_2_rename",
        "sections": [
            {"slug": "pain", "heading": "課題",
             "facts": ["資料探索に平均 8 分かかるという回答が最多だった。"]},
            {"slug": "quote", "heading": "生の声",
             "facts": ["「3ヶ月前のあの資料が見つからない」という声が複数あった。"]},
        ],
    },

    # === M3-2: 編集される anchor (現行名のまま。旧値は履歴のみ。--all-history) ===
    {
        "scope": "research", "file": "model-selection.md",
        "title": "モデル選定メモ", "role": "m3_2_edit",
        "sections": [
            {"slug": "chosen", "heading": "採用モデル",
             # 旧値: Harrier / 0.71。replay で Condor / 0.79 に編集。
             "facts": ["一次選定では Harrier を採用、暫定スコア 0.71 とした。"]},
            {"slug": "rejected", "heading": "見送りモデル",
             "facts": ["Suzaku はコスト過大のため見送りとした。"]},
        ],
    },
    {
        "scope": "notes", "file": "budget-review.md",
        "title": "予算レビュー議事録", "role": "m3_2_edit",
        "sections": [
            {"slug": "total", "heading": "合計予算",
             # 旧値: 750万円。replay で 920万円 に編集。
             "facts": ["レビュー時点の合計予算は 750万円 と報告された。"]},
            {"slug": "breakdown", "heading": "内訳",
             "facts": ["内訳は人件費 60%、クラウド 25%、その他 15%。"]},
        ],
    },
    {
        "scope": "downloads", "file": "benchmark-draft.md",
        "title": "ベンチマーク下書き", "role": "m3_2_edit",
        "sections": [
            {"slug": "score", "heading": "暫定スコア",
             # 旧値: 0.71。replay で 0.79 に編集。
             "facts": ["Tsubame 構成の暫定スコアは 0.71 だった。"]},
            {"slug": "setup", "heading": "計測環境",
             "facts": ["計測は 8 vCPU / 32GB の環境で実施した。"]},
        ],
    },

    # === M3-3: 削除される anchor (削除済みの数字を再発見。--include-deleted) ===
    {
        "scope": "research", "file": "deprecated-approach.md",
        "title": "廃止した検索手法", "role": "m3_3_delete",
        "sections": [
            {"slug": "method", "heading": "旧手法",
             "facts": ["旧手法は TF-IDF、語彙次元は 30,000 だった。"]},
            {"slug": "result", "heading": "結果",
             "facts": ["旧手法の Recall@10 は 0.52 に留まった。"]},
        ],
    },
    {
        "scope": "notes", "file": "cancelled-project-osprey.md",
        "title": "中止プロジェクト Osprey 記録", "role": "m3_3_delete",
        "sections": [
            {"slug": "loss", "heading": "損失",
             "facts": ["Osprey 中止に伴う損失は 210万円 と算定された。"]},
            {"slug": "reason", "heading": "中止理由",
             "facts": ["需要不足と体制縮小が中止理由。"]},
        ],
    },
    {
        "scope": "downloads", "file": "old-api-limits.md",
        "title": "旧 API リミット表", "role": "m3_3_delete",
        "sections": [
            {"slug": "limits", "heading": "旧リミット",
             "facts": ["旧レート制限は 1,000 req/min だった。"]},
            {"slug": "quota", "heading": "旧クォータ",
             "facts": ["月間クォータは 200万コール だった。"]},
        ],
    },
    {
        "scope": "downloads", "file": "leaked-draft-pricing.md",
        "title": "価格改定ドラフト (誤取込)", "role": "m3_3_delete",
        "sections": [
            {"slug": "price", "heading": "旧価格",
             "facts": ["旧価格は 1,000 トークンあたり 0.30 USD だった。"]},
            {"slug": "discount", "heading": "割引",
             "facts": ["年契約割引は 40% を提示していた。"]},
        ],
    },
    {
        "scope": "projects-a", "file": "falcon-incident-0421.md",
        "title": "Falcon 障害報告 04-21", "role": "m3_3_delete",
        "sections": [
            {"slug": "outage", "heading": "影響",
             "facts": ["サービス停止は 47 分に及んだ。"]},
            {"slug": "rootcause", "heading": "原因",
             "facts": ["原因はメモリリーク、ピークで 3.2GB まで増加した。"]},
        ],
    },
    {
        "scope": "projects-a", "file": "falcon-old-schema.md",
        "title": "Falcon 旧スキーマ", "role": "m3_3_delete",
        "sections": [
            {"slug": "tables", "heading": "旧テーブル",
             "facts": ["旧スキーマは 28 テーブル構成だった。"]},
            {"slug": "index", "heading": "旧インデックス",
             "facts": ["旧インデックスは B-tree のみで 9 本。"]},
        ],
    },
    {
        "scope": "projects-b", "file": "kestrel-poc-metrics.md",
        "title": "Kestrel PoC 計測", "role": "m3_3_delete",
        "sections": [
            {"slug": "latency", "heading": "PoC レイテンシ",
             "facts": ["PoC の p95 は 1,900ms と遅かった。"]},
            {"slug": "cost", "heading": "PoC コスト",
             "facts": ["PoC 期間の月額コストは 68万円 だった。"]},
        ],
    },
    {
        "scope": "specs", "file": "legacy-format-v0.md",
        "title": "旧フォーマット v0 仕様", "role": "m3_3_delete",
        "sections": [
            {"slug": "version", "heading": "廃止バージョン",
             "facts": ["v0.1.0 は廃止済み。kio_format_version に統一された。"]},
            {"slug": "field", "heading": "廃止フィールド",
             "facts": ["旧フィールド tree_id / commit_id は廃止された。"]},
        ],
    },
    {
        "scope": "journal", "file": "scratch-numbers.md",
        "title": "試算メモ (走り書き)", "role": "m3_3_delete",
        "sections": [
            {"slug": "estimate", "heading": "試算",
             "facts": ["試算では 4,096 次元・12万チャンク を仮定した。"]},
            {"slug": "todo", "heading": "TODO",
             "facts": ["次元と本数は要検証、暫定値。"]},
        ],
    },
]


# --- 履歴シナリオ (replay_history.py が適用する決定論的な操作列) ---------------
# edits: 該当 section 内の old_value を new_value に置換 (現行 tree は new_value)。
# renames: 原名 old_file を new_file へリネーム (現行 tree は new_file)。
# deletes: 原名 file を削除 (現行 tree から消える。CAS には残る)。

HISTORY = {
    "renames": [
        {"scope": "research", "old_file": "auth-spec.md", "new_file": "authentication-guide.md"},
        {"scope": "notes", "old_file": "vendor-eval.md", "new_file": "supplier-assessment.md"},
        {"scope": "downloads", "old_file": "rag-pipeline.md", "new_file": "retrieval-pipeline.md"},
        {"scope": "projects-a", "old_file": "falcon-migration.md", "new_file": "falcon-cutover-plan.md"},
        {"scope": "projects-b", "old_file": "kestrel-security.md", "new_file": "kestrel-threat-model.md"},
        {"scope": "specs", "old_file": "evidence-pointer-spec.md", "new_file": "evidence-pointer-contract.md"},
        {"scope": "journal", "old_file": "interview-notes.md", "new_file": "user-research-summary.md"},
    ],
    "edits": [
        {"scope": "research", "file": "model-selection.md",
         "old_value": "一次選定では Harrier を採用、暫定スコア 0.71 とした。",
         "new_value": "最終選定では Condor を採用、確定スコア 0.79 とした。"},
        {"scope": "notes", "file": "budget-review.md",
         "old_value": "レビュー時点の合計予算は 750万円 と報告された。",
         "new_value": "改定後の合計予算は 920万円 と報告された。"},
        {"scope": "downloads", "file": "benchmark-draft.md",
         "old_value": "Tsubame 構成の暫定スコアは 0.71 だった。",
         "new_value": "Tsubame 構成の確定スコアは 0.79 だった。"},
    ],
    "deletes": [
        {"scope": "research", "file": "deprecated-approach.md"},
        {"scope": "notes", "file": "cancelled-project-osprey.md"},
        {"scope": "downloads", "file": "old-api-limits.md"},
        {"scope": "downloads", "file": "leaked-draft-pricing.md"},
        {"scope": "projects-a", "file": "falcon-incident-0421.md"},
        {"scope": "projects-a", "file": "falcon-old-schema.md"},
        {"scope": "projects-b", "file": "kestrel-poc-metrics.md"},
        {"scope": "specs", "file": "legacy-format-v0.md"},
        {"scope": "journal", "file": "scratch-numbers.md"},
    ],
}


# --- レンダリング -------------------------------------------------------------
def render_anchor(anchor):
    """anchor 定義から決定論的な Markdown 本文を生成する."""
    rng = random.Random(_seed_int("anchor", anchor["scope"], anchor["file"]))
    lines = [f"# {anchor['title']}", ""]
    lines.append(_paragraph(rng, 2))
    lines.append("")
    for sec in anchor["sections"]:
        lines.append(f"## {sec['heading']}")
        lines.append("")
        for fact in sec["facts"]:
            lines.append(fact)
        # section を埋没させないための軽い filler (facts の後)。
        lines.append(_paragraph(rng, 2))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def anchor_manifest_entry(anchor):
    return {
        "scope": anchor["scope"],
        "file": anchor["file"],
        "kind": "md",
        "anchor": True,
        "role": anchor["role"],
        "sections": [{"slug": s["slug"], "heading": s["heading"]} for s in anchor["sections"]],
    }


# --- filler 生成 --------------------------------------------------------------
_FILLER_TOPICS = [
    "運用メモ", "調査ノート", "設計メモ", "打合せ記録", "検証ログ",
    "リリースノート", "パフォーマンス記録", "移行手順", "レビュー指摘", "見積草案",
]


def _filler_pdf_bytes(title, body_lines):
    """ASCII 英語の text-native な最小 PDF を生成 (pipeline の text-layer 抽出対象)."""
    content = "BT\n/F1 12 Tf\n72 720 Td\n14 TL\n"
    for ln in [title] + body_lines:
        esc = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content += f"({esc}) Tj\nT*\n"
    content += "ET"
    cb = content.encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(cb) + cb + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objs) + 1, xref)
    return out


def filler_files(scope):
    """scope の filler 文書を決定論的に生成する.

    返り値: list of dict {file, kind, is_binary, text|data, sections}.
    """
    count = FILLER_PER_SCOPE[scope]
    n_pdf = FILLER_PDF_PER_SCOPE
    out = []
    for i in range(count):
        rng = random.Random(_seed_int("filler", scope, i))
        idx = i + 1
        if i < n_pdf:
            # ASCII 英語 text-native PDF (クエリ対象外、形式多様性のため)。
            code = rng.choice(CODENAMES)
            num = rng.choice([120, 256, 512, 1024, 3200, 4096])
            title = f"{code} operations note {idx:04d}"
            body = [
                f"Metric {j}: {code} sustained {num + j * 7} units per interval."
                for j in range(1, 5)
            ]
            out.append({
                "file": f"ops-note-{idx:04d}.pdf",
                "kind": "pdf",
                "is_binary": True,
                "data": _filler_pdf_bytes(title, body),
                "sections": [],
            })
            continue
        topic = rng.choice(_FILLER_TOPICS)
        kind = "txt" if i % 5 == 0 else "md"
        n_sec = rng.randint(2, 3)
        secs = []
        if kind == "md":
            lines = [f"# {topic} {idx:04d}", "", _paragraph(rng, 2), ""]
            for s in range(n_sec):
                slug = f"sec-{s+1}"
                heading = rng.choice(JA_TERMS) + f" {s+1}"
                lines.append(f"## {heading}")
                lines.append("")
                lines.append(_paragraph(rng, rng.randint(2, 4)))
                lines.append("")
                secs.append({"slug": slug, "heading": heading})
            text = "\n".join(lines).rstrip() + "\n"
            fname = f"{['memo','log','draft','note'][i % 4]}-{idx:04d}.md"
        else:
            para = "\n\n".join(_paragraph(rng, rng.randint(3, 5)) for _ in range(n_sec))
            text = f"{topic} {idx:04d}\n\n{para}\n"
            fname = f"plain-{idx:04d}.txt"
        out.append({
            "file": fname,
            "kind": kind,
            "is_binary": False,
            "text": text,
            "sections": secs,
        })
    return out


# --- 集計ヘルパ ---------------------------------------------------------------
def total_file_count():
    return len(ANCHORS) + sum(FILLER_PER_SCOPE.values())


def anchors_by_role(role):
    return [a for a in ANCHORS if a["role"] == role]
