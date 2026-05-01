# Markdown Processing Adapter

> 正本: `adapter-overview.md`。Markdown 化は OCR と並列の処理ではなく、OCR を必要に応じて内包する Markdown 処理として扱う。

## 役割

Markdown 処理 Adapter は raw object を Normalized Markdown artifact に変換する。対象は text-native な Markdown / txt だけでなく、PDF、Office 文書、画像、音声を含む。

```text
raw object
  -> prepared unit
  -> Markdown processing Adapter
  -> normalized Markdown
```

画像やスキャン PDF の OCR、レイアウト解析、表抽出、音声文字起こしは、この Adapter の内部 capability として記録する。

## Profile

```text
markdown_profile_hash:
  adapter_id
  tool_family
  version
  capability_flags
  normalization_rules_version
```

`capability_flags` には `ocr`、`layout_detection`、`table_extraction`、`speech_to_text` などを含められる。
