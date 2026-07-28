```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Run 001 dashboard check\n",
        "\n",
        "Quick review of the median signal trace before the team readout.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "import pandas as pd\n",
        "plate = pd.read_csv('cohort-a_cycle_reads.csv')\n",
        "plate.groupby('cycle', as_index=False)['signal_au'].median()\n"
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
