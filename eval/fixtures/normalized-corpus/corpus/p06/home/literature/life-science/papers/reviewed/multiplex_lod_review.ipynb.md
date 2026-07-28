```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Multiplex LOD literature review\n",
        "\n",
        "Compact comparison used to frame the current method discussion.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "import pandas as pd\n",
        "papers = pd.DataFrame({'method': ['bead', 'MS', 'ELISA'], 'reported_lod_pg_ml': [8, 14, 21]})\n",
        "papers.sort_values('reported_lod_pg_ml')\n"
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
