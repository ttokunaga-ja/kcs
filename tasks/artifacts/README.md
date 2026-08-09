# 保全した再現条件 (PaddleOCR-VL)

`crates/kio-adapter/tests/fixtures/layout-parsing/` の 9 本のキャプチャを採った
サービスそのものの設定である。**第 1〜5 回のすべてがこの 2 イメージで採られている。**

置いてある理由は、これが**一時ディレクトリにしか無かった**ため。`tasks/gpu-local-ocr-verification.md`
は compose 一式を `~/paddleocr-vl` に置く手順を書いているが、実際には
`AppData\Local\Temp\...\scratchpad\paddleocr-vl` に作られていた。2026-08-09 に
「この機から消えた」と判断されたのはそのためで、実際には残っていた。
掃除されれば消えるので、原本をここへ移した (再構成ではない)。

| ファイル | 中身 |
|---|---|
| `paddleocr-vl-compose/compose.yaml` | 上流の compose 原本。イメージは**タグ**参照 |
| `paddleocr-vl-compose/compose.override.yaml` | 12 GB カード向けの上書き (`shm_size` / `backend_config`) |
| `paddleocr-vl-compose/backend-config.yaml` | **これが無いと起動しない。**下記 |
| `paddleocr-vl-compose/env.txt` | 元は `.env`。タグ接尾辞の変数 3 つ |
| `paddleocr-vl-compose/compose.pinned.yaml` | 上の 4 つを 1 本にまとめ、**digest 固定**したもの |
| `paddleocr-pipeline-inspect.json` | `docker inspect` 全文 (pipeline) |
| `paddleocr-vllm-inspect.json` | `docker inspect` 全文 (VLM) |
| `paddleocr-docker-ps.txt` | `docker ps --no-trunc` |

## 再現するなら `compose.pinned.yaml` を使うこと

`compose.yaml` はイメージを `latest-nvidia-gpu-offline` という**タグ**で参照している。
タグは動く。**タグのまま保全すると、手順は残るが中身は残らない。**
`compose.pinned.yaml` は同じ構成を digest で固定してある:

| | digest |
|---|---|
| Pipeline | `sha256:6c735bdf9e758ffdd58ccc067db0c2d84e37e5e6a2cbd47156069d4d7ea5d709` |
| VLM | `sha256:d0d32c04a2119613d25a0a4c292e165ccc107954b74580613cf59e378037f8f5` |

重みの sha256 (`85a479d5…71db`) はコード側 (`LOCAL_OCR_MODEL_VERSION_PIN`) が
凍結しているので、イメージを差し替えたら必ず取り直して突き合わせること。

## `backend-config.yaml` が要点である

**`docker inspect` からは復元できない唯一のもの**がこれである。inspect には
マウント**先のパス** (`/cfg/backend-config.yaml`) は載るが、**中身の 789 バイトは
載らない**。そして上流既定 (`gpu_memory_utilization 0.5` /
`max_num_batched_tokens 131072`) は 12 GB のカードでは KV キャッシュが負になり、
**エンジンが起動しない**。

つまり inspect だけから compose を復元すると、**存在しないファイルを参照して
立ち上がらないもの**が出来る。原本が残っていたのは運がよかっただけである。

**この repo のキャプチャはすべて既定設定の応答ではない**という意味でもある
(`gpu_memory_utilization: 0.85` / `max_model_len: 16384` /
`max_num_batched_tokens: 16384` / `api_server_count: 1`)。
サンプリングにもテンプレートにも重みにも触っていないが、
「上流の既定で再現する」とは書けない。

## inspect について 2 点

- **資格情報は入っていない。**`GPG_KEY` は python 公式イメージが持つ**公開**署名鍵の
  フィンガープリントで、秘密ではない。
- **env は compose 由来とイメージ由来が混ざっている。**`VLM_BACKEND` / `BACKEND` は
  compose が入れたもので、`PATH` / `GPG_KEY` / `PYTHON_VERSION` などはイメージ由来。
  イメージの `Config.Env` と差分を取らないと分離できないので、inspect の
  `Config.Env` をそのまま compose の `environment:` に写さないこと。
