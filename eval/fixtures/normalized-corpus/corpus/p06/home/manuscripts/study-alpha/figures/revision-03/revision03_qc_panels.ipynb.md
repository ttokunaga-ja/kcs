```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Revision 03 QC panels\n",
        "\n",
        "Preparation cell for the manuscript QC panel refresh.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "import pandas as pd\n",
        "panel = pd.read_csv('cohort-a_cycle_reads.csv')\n",
        "panel.groupby('cycle')['signal_au'].agg(['median', 'std'])\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Analyst note\n",
        "\n",
        "Keep the plate-level inputs unchanged; this notebook only prepares a review view.\n"
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
