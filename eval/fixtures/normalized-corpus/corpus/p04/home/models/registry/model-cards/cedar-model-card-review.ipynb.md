```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Cedar model-card review\n",
        "\n",
        "Keeps the candidate and robust baseline aligned to one collection revision and one judge-set description.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "packages = [\n",
        "    {\"name\": \"model-alpha\", \"role\": \"candidate\"},\n",
        "    {\"name\": \"model-beta\", \"role\": \"robust baseline\"},\n",
        "]\n",
        "{item[\"name\"]: item[\"role\"] for item in packages}\n"
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
