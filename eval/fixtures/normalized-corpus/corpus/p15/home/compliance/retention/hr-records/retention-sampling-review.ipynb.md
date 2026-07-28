```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Recruitment record retention sampling\\n",
        "\\n",
        "July spot check for Atlas candidate packets. The notebook reads a local export only and writes no changes.\\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": 1,
      "metadata": {},
      "outputs": [
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "Reviewed 24 packet labels; 2 require owner confirmation.\\n"
          ]
        }
      ],
      "source": [
        "from collections import Counter\\n",
        "labels = ['active', 'active', 'archive-review'] * 8\\n",
        "Counter(labels)\\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Observation\\n",
        "\\n",
        "The remaining confirmations are both linked to expired sharing permissions, not to retention-period changes.\\n"
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
