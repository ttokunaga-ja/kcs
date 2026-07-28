```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Weekly KPI review\n",
        "\n",
        "A compact working notebook for the Monday Commercial Intelligence review. It aligns sales, operations, and product signals before the planning refresh discussion.\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Load closed-week metrics\n"
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
        "sales = pd.read_csv(\"sales_closed_week.csv\")\n",
        "operations = pd.read_csv(\"operations_closed_week.csv\")\n",
        "product = pd.read_csv(\"product_closed_week.csv\")\n",
        "sales.head()\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Create a decision view\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "view = sales.merge(operations, on=[\"week_start\", \"market_code\"], how=\"left\")\n",
        "view = view.merge(product, on=[\"week_start\", \"market_code\"], how=\"left\")\n",
        "view[\"margin_rate\"] = view[\"fulfillment_margin\"] / view[\"recognized_net_sales\"]\n",
        "view.sort_values(\"recognized_net_sales\", ascending=False).head(10)\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Flag discussion rows\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "discussion = view.query(\"margin_rate < 0.12 or activation_rate < 0.18\")\n",
        "print(f\"rows to discuss: {len(discussion)}\")\n"
      ]
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}
```
