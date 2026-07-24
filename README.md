# Kio

> **Local-first knowledge archive, powered by frontier AI.**
> データはローカル、計算は最強の AI を使う。

Kio indexes the files you already have — PDFs, Office documents, images, code,
notes — and makes them searchable with evidence you can follow back to the
original bytes. Your data stays on your machine. The heavy lifting (OCR,
embedding) uses frontier models, on explicit opt-in.

Secondary framing: *evidence-grounded local knowledge archive*.

**Status: pre-release.** The MVP pipeline is implemented and passes its contract
suite, but there are no published binaries yet and the CLI surface can still
change. It is a CLI; there is no GUI.

---

## What it does differently

**1. Evidence Pointer.** Results point at `commit / tree / raw_hash /
chunk_hash / span`, not at a path. Move the file, rename it, or delete it, and
the citation still resolves. Paths rot; content addresses do not.

**2. Markdown normalization.** Every format is converted to normalized Markdown,
so a human and a model read the same view of a scanned PDF, a slide deck, and a
source file.

**3. Content-addressed store.** Files are kept as CAS objects, so past versions,
moved files, and deleted files remain reachable — except where you explicitly
`purge` or `erase` them.

## Who it is for

Developers, researchers, and engineers with a large, messy pile of local files,
who are comfortable with a CLI, and who want AI-assisted search without handing
the whole archive to someone else's cloud.

## Quick start

```bash
kio init
kio index --approve      # ingest + baseline index (snapshots on success)
kio search "あの PDF"
kio open <pointer from the results>
```

## About network use

Kio is **local-first**, which means your originals, history, and index live on
your machine — it does not mean the tool refuses to use the network.

OCR and embedding send file contents to external adapters (Mistral OCR, Gemini,
and others). That happens **only after you explicitly opt in**, the CLI shows a
network transmission policy in its preview before it happens, and Kio records
what was sent, when, and to which adapter. Fully offline operation remains
possible by choosing local or deterministic adapters, but it is not the default.

See [docs/07-adapter-spec.md](docs/07-adapter-spec.md) for the opt-in scope,
lifetime, and revocation rules.

## Documentation

[docs/README.md](docs/README.md) is the entry point and defines the reading
order. The numbered files under `docs/` are the **normative specification** —
the implementation follows them, not the other way around.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Kio is dual-licensed, so contributions
are covered by a CLA; please read it before opening a pull request.

## License

Kio is source-available under the
[PolyForm Shield License 1.0.0](LICENSE.md).

You may use, modify, and distribute Kio for **any purpose except providing a
product that competes with Kio**. In practice that permits personal use,
internal company use at any scale, research, private forks, and building
non-competing products on top of it — and reserves reselling Kio as a competing
product.

For competing use, a separate commercial license is available. See
[COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

The name "Kio" is a trademark and is not licensed by the source license — see
[TRADEMARKS.md](TRADEMARKS.md). **If you distribute a modified version, rename
it.**

Required Notice: Copyright 2026 TOKUNAGA Takumi (https://github.com/ttokunaga-ja/kio)

---

# 日本語

Kio は、手元にある PDF・Office 文書・画像・コード・メモをそのまま索引化し、
**原文の根拠まで辿れる検索**を提供するローカル知識アーカイブです。データの主権は
あなたのマシンにあり、OCR や Embedding といった重い計算には frontier AI を使います
(明示的な opt-in 後)。

**状態: プレリリース。** MVP パイプラインは実装済みで契約テストを通過していますが、
配布バイナリはまだなく、CLI の仕様も変わりえます。GUI はありません。

## 中核 3 点

1. **Evidence Pointer** — 検索結果は path ではなく `commit / tree / raw_hash /
   chunk_hash / span` を指します。ファイルを移動・改名・削除しても根拠は解決できます。
2. **Markdown 正規化** — 全形式を正規化 Markdown に変換し、人間と AI が同じビューを見ます。
3. **Content-addressed CAS** — 過去版・移動済み・削除済みのファイルにも到達できます
   (明示的な `purge` / `erase` を除く)。

## 対象ユーザー

大量の PDF・Markdown・コード・画像・研究資料を扱う開発者・研究者・技術者で、CLI に抵抗がなく、
AI 検索は試したいがアーカイブ全体をクラウドに丸投げしたくない層。

## ネットワーク利用について

**local-first** は「データの主権がローカルにある」という意味であり、「ネットを使わない」
という意味ではありません。OCR と Embedding では外部 Adapter へファイル内容が送信されます。
これは**明示的な opt-in の後にのみ**発生し、実行前に network transmission policy として
preview で提示され、何を・いつ・どの Adapter へ送ったかが記録されます。完全オフライン運用も
選択可能ですが、既定ではありません。

## ライセンス

Kio は [PolyForm Shield License 1.0.0](LICENSE.md) の下で source-available として公開しています。

**Kio と競合する製品の提供を除く、あらゆる用途**で利用・改変・再頒布が可能です。個人利用、
企業規模を問わない社内利用、研究、非公開フォーク、非競合製品の開発は許諾されます。
競合用途には別途 [商用ライセンス](COMMERCIAL-LICENSE.md) をご用意しています。

「Kio」の名称は商標であり、ソースライセンスでは許諾されません
([TRADEMARKS.md](TRADEMARKS.md))。**改変版を頒布する場合は改名してください。**
