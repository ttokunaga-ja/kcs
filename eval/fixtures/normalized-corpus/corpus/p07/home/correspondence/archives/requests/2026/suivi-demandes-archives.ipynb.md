```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Suivi des demandes d'archives\n",
        "\n",
        "Carnet de travail pour relire les réponses reçues au sujet du fonds Keller-Roth. Les résultats servent seulement à préparer les relances et à repérer les pièces dont la provenance doit être vérifiée."
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "from collections import Counter\n",
        "\n",
        "responses = [\n",
        "    {'institution': 'Northshore Manuscript Archive', 'status': 'replied'},\n",
        "    {'institution': 'Bibliothèque du Littoral', 'status': 'follow-up'},\n",
        "]\n",
        "Counter(row['status'] for row in responses)"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## À faire\n",
        "\n",
        "- relire les conditions de consultation;\n",
        "- distinguer les réponses définitives des demandes incomplètes;\n",
        "- reporter les références confirmées dans le tableau des sources."
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
      "version": "3"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5
}
```
