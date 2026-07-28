```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Ranking evaluation protocol examples\n",
        "\n",
        "Compares packages only after collection revision, judge set, and duplicate suppression agree.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "left = {\"collection\": \"cedar-docs-r12\", \"judges\": \"editorial-holdout-v5\", \"dedupe\": True}\n",
        "right = {\"collection\": \"cedar-docs-r12\", \"judges\": \"editorial-holdout-v5\", \"dedupe\": True}\n",
        "left == right\n"
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
