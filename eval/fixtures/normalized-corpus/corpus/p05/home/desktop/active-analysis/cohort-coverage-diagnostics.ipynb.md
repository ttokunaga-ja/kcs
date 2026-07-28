```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Cohort coverage diagnostics\n",
        "\n",
        "Q2 planning refresh 用の cohort 抽出が、market と channel をまたいで偏っていないかを確認する。対象は Harborline Storefront の確定済み buyer activity。\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## 読み込みと対象週の固定\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "import pandas as pd\n",
        "\n",
        "cohort = pd.read_parquet(\"../staging/buyer_week.parquet\")\n",
        "closed = cohort.query(\"week_start <= '2026-06-29'\").copy()\n",
        "closed[\"is_active\"] = closed[\"order_count\"].gt(0)\n",
        "closed.groupby([\"week_start\", \"market_code\", \"channel\"])[\"is_active\"].sum().head()\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## coverage の確認\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "coverage = (\n",
        "    closed.groupby([\"market_code\", \"channel\"], as_index=False)\n",
        "    .agg(eligible_buyers=(\"buyer_key\", \"nunique\"), active_buyers=(\"is_active\", \"sum\"))\n",
        ")\n",
        "coverage[\"active_rate\"] = coverage[\"active_buyers\"] / coverage[\"eligible_buyers\"]\n",
        "coverage.sort_values(\"active_rate\")\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## レビュー用の印\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "low_coverage = coverage.query(\"eligible_buyers < 500\")\n",
        "if not low_coverage.empty:\n",
        "    print(\"小さい cohort は比較注記を付ける\")\n"
      ]
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}
```
