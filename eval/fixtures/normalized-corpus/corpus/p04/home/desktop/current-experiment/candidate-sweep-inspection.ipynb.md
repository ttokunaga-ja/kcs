```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Candidate sweep inspection\n",
        "\n",
        "Checks configuration coverage before model-alpha review jobs are queued.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "candidates = [\n",
        "    {\"learning_rate\": 2.0e-5, \"hard_negative_mix\": 0.28},\n",
        "    {\"learning_rate\": 2.5e-5, \"hard_negative_mix\": 0.34},\n",
        "    {\"learning_rate\": 3.0e-5, \"hard_negative_mix\": 0.40},\n",
        "]\n",
        "len(candidates)\n"
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
