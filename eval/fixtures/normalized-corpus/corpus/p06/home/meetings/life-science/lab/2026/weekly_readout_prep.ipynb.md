```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Weekly assay readout preparation\n",
        "\n",
        "Checklist notebook for the Monday research operations readout.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "from pathlib import Path\n",
        "exports = sorted(Path('.').glob('*.csv'))\n",
        "[p.name for p in exports]\n"
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
