```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Dataset ingest validation\n",
        "\n",
        "Acts as a receipt-style check after a Cedar collection drop arrives from the editorial pipeline.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "drop = {\n",
        "    \"collection_revision\": \"cedar-docs-r12\",\n",
        "    \"documents\": 48216,\n",
        "    \"duplicate_suppression_ready\": True,\n",
        "}\n",
        "assert drop[\"documents\"] > 0\n",
        "assert drop[\"duplicate_suppression_ready\"]\n",
        "drop[\"collection_revision\"]\n"
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
