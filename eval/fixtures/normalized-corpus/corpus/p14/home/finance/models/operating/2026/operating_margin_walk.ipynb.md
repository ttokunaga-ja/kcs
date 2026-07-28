```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# FY2026 operating margin walk\n",
        "\n",
        "Working notebook for the Q2 planning refresh. It reconciles the approved base case with March close inputs after department mappings are normalised."
      ]
    },
    {
      "cell_type": "code",
      "execution_count": 1,
      "metadata": {},
      "outputs": [],
      "source": [
        "import pandas as pd\n",
        "\n",
        "close = pd.read_csv(\"orion_gl_202603_final.csv\")\n",
        "mapping = pd.read_csv(\"cost_center_map_202604.csv\")\n",
        "model = close.merge(mapping, on=\"department_code\", how=\"left\")\n",
        "assert model[\"reporting_department\"].notna().all()\n",
        "model.head()"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Review notes\n",
        "\n",
        "- Carrier-rate sensitivity is maintained separately from confirmed service receipts.\n",
        "- West Tokyo distribution-centre timing remains a scenario driver.\n",
        "- Unapproved commercial opportunities are excluded from the base case."
      ]
    },
    {
      "cell_type": "code",
      "execution_count": 2,
      "metadata": {},
      "outputs": [
        {
          "name": "stdout",
          "output_type": "stream",
          "text": [
            "rows reconciled: 18426\\n",
            "unmapped departments: 0\\n"
          ]
        }
      ],
      "source": [
        "summary = (\n",
        "    model.groupby(\"reporting_department\", as_index=False)[\"amount_jpy\"]\n",
        "    .sum()\n",
        "    .sort_values(\"amount_jpy\", ascending=False)\n",
        ")\n",
        "print(f\"rows reconciled: {len(model)}\")\n",
        "print(f\"unmapped departments: {model['reporting_department'].isna().sum()}\")"
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
      "version": "3.12"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5
}
```
