```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Lab update figures\n",
        "\n",
        "Prepares a compact trend figure for the Applied Foundations weekly Cedar review.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "import matplotlib.pyplot as plt\n",
        "\n",
        "weeks = [\"Jun 26\", \"Jul 3\", \"Jul 10\", \"Jul 18\"]\n",
        "review_completion = [72, 79, 83, 88]\n",
        "fig, ax = plt.subplots(figsize=(6, 3))\n",
        "ax.plot(weeks, review_completion, marker=\"o\", color=\"#2e6f95\")\n",
        "ax.set_ylabel(\"Review completion (%)\")\n",
        "fig.tight_layout()\n"
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
