```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# CRM activity cleanup\n",
        "\n",
        "営業担当から受け取った CRM activity export を、Commercial Intelligence の weekly review に載せられる形へ整える。個人名は共有前に落とし、market と activity type だけを残す。\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Extract normalization\n"
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
        "raw = pd.read_csv(\"crm_activity_export.csv\")\n",
        "raw.columns = [column.strip().lower().replace(\" \", \"_\") for column in raw.columns]\n",
        "cleaned = raw.dropna(subset=[\"activity_date\", \"market_code\", \"activity_type\"]).copy()\n",
        "cleaned[\"activity_date\"] = pd.to_datetime(cleaned[\"activity_date\"]).dt.date\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Remove contact detail\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "review_columns = [\"activity_date\", \"market_code\", \"activity_type\", \"campaign_family\"]\n",
        "review = cleaned.reindex(columns=review_columns).drop_duplicates()\n",
        "review.sort_values([\"activity_date\", \"market_code\"]).head()\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Quality note\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "unknown_market = review[review[\"market_code\"].eq(\"unknown\")]\n",
        "print(f\"unknown market rows: {len(unknown_market)}\")\n"
      ]
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}
```
