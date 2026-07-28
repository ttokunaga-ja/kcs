```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Snapshot quality check\n",
        "\n",
        "日次 snapshot の行数・watermark・主要列の null を確認し、朝会で説明できる状態にする。Harborline Storefront の sales と operations の refresh を同じ表で見る。\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Load snapshot register\n"
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
        "register = pd.read_csv(\"snapshot_register.csv\")\n",
        "register[\"loaded_at\"] = pd.to_datetime(register[\"loaded_at\"])\n",
        "register.sort_values(\"loaded_at\").tail()\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Check completeness\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "checks = (\n",
        "    register.groupby(\"mart\", as_index=False)\n",
        "    .agg(rows=(\"row_count\", \"sum\"), latest_load=(\"loaded_at\", \"max\"), null_sales=(\"null_sales\", \"sum\"))\n",
        ")\n",
        "checks[\"ready\"] = checks[\"null_sales\"].eq(0) & checks[\"rows\"].gt(0)\n",
        "checks\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Prepare morning note\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "not_ready = checks.loc[~checks[\"ready\"], \"mart\"].tolist()\n",
        "print(\"ready\" if not not_ready else f\"review needed: {', '.join(not_ready)}\")\n"
      ]
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}
```
