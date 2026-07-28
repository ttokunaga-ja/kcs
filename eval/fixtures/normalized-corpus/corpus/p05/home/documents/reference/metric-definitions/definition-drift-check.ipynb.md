```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Definition drift check\n",
        "\n",
        "This notebook compares the published semantic definitions with the fields emitted by the warehouse marts. It is a review aid for the Commercial Intelligence team, not a deployment step.\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Load the reference tables\n"
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
        "catalog = pd.read_csv(\"metric_catalog_export.csv\")\n",
        "columns = pd.read_csv(\"warehouse_columns.csv\")\n",
        "expected = catalog[[\"metric_key\", \"canonical_grain\", \"description\"]].drop_duplicates()\n",
        "expected.head()\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Compare canonical grain\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "comparison = expected.merge(columns, on=\"metric_key\", how=\"left\")\n",
        "comparison[\"grain_matches\"] = comparison[\"canonical_grain\"].eq(comparison[\"observed_grain\"])\n",
        "comparison.loc[~comparison[\"grain_matches\"], [\"metric_key\", \"canonical_grain\", \"observed_grain\"]]\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Prepare handoff notes\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "review = comparison.query(\"not grain_matches\")\n",
        "print(f\"{len(review)} definitions need an owner review\")\n"
      ]
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}
```
