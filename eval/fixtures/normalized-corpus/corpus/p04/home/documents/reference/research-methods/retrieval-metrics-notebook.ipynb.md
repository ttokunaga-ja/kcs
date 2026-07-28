```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Retrieval metric reference\n",
        "\n",
        "Holds small, readable examples used when explaining Cedar metrics to reviewers.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "def reciprocal_rank(relevant_positions):\n",
        "    first = min(relevant_positions, default=None)\n",
        "    return 0.0 if first is None else 1.0 / first\n",
        "\n",
        "reciprocal_rank([3, 8])\n"
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
