```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# 匿名化済み AE 模擬データの作成\n",
        "\n",
        "ORCHID-CKD-201 Alpha の安全性レビュー手順を確認するための、研究用キーだけを含む模擬データです。臨床判断や実患者の記録には使用しません。"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "from collections import Counter\n",
        "from datetime import date, timedelta\n",
        "from random import Random\n",
        "\n",
        "rng = Random(20260718)\n",
        "STUDY = 'ORCHID-CKD-201'\n",
        "SITE = 'MMC-03'\n",
        "TERMS = ['nausea', 'fatigue', 'dizziness', 'pruritus']\n",
        "STATUSES = ['open', 'under_medical_review', 'resolved']\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "def build_events(participant_count: int = 8) -> list[dict]:\n",
        "    baseline = date(2026, 7, 1)\n",
        "    events = []\n",
        "    for offset in range(participant_count):\n",
        "        participant_key = f'A03-{offset + 1:03d}'\n",
        "        event_count = 1 if rng.random() < 0.65 else 0\n",
        "        for sequence in range(event_count):\n",
        "            events.append({\n",
        "                'study': STUDY,\n",
        "                'site': SITE,\n",
        "                'participant_key': participant_key,\n",
        "                'event_term': rng.choice(TERMS),\n",
        "                'onset_date': (baseline + timedelta(days=rng.randrange(0, 20))).isoformat(),\n",
        "                'status': rng.choice(STATUSES),\n",
        "                'is_training_record': True,\n",
        "            })\n",
        "    return events\n",
        "\n",
        "events = build_events()\n",
        "term_summary = Counter(event['event_term'] for event in events)\n",
        "term_summary\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## 確認事項\n",
        "\n",
        "- 出力には氏名、連絡先、院内識別子を含めない。\n",
        "- event term と review status の組合せが安全性一覧で読めることを確認する。\n",
        "- 実運用に渡す前に、このノートブックの生成結果は破棄する。"
      ]
    }
  ],
  "metadata": {
    "kernelspec": {
      "display_name": "Python 3",
      "language": "python",
      "name": "python3"
    },
    "language_info": {
      "name": "python",
      "version": "3.11"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5
}
```
