```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Demand intake triage\n",
        "\n",
        "This working notebook groups active stakeholder asks for the Commercial Intelligence queue. It is used to decide whether a request belongs in the sales dashboard, an operations bridge, or a planning memo.\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Read the intake export\n"
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
        "intake = pd.read_csv(\"active_intake.csv\")\n",
        "intake[\"received_at\"] = pd.to_datetime(intake[\"received_at\"])\n",
        "intake[[\"area\", \"request_summary\", \"priority\"]].head()\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Assign a review lane\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "lane_map = {\n",
        "    \"sales\": \"dashboard\",\n",
        "    \"operations\": \"margin bridge\",\n",
        "    \"product\": \"metric definition\",\n",
        "}\n",
        "intake[\"review_lane\"] = intake[\"area\"].map(lane_map).fillna(\"planning memo\")\n",
        "intake.groupby(\"review_lane\").size().sort_values(ascending=False)\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Surface blockers\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "blocked = intake.query(\"status == 'waiting'\")\n",
        "print(f\"waiting on stakeholder input: {len(blocked)}\")\n"
      ]
    }
  ],
  "metadata": {},
  "nbformat": 4,
  "nbformat_minor": 5
}
```
