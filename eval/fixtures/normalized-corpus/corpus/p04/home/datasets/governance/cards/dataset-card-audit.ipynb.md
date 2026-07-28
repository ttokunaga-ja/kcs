```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Cedar dataset-card audit\n",
        "\n",
        "Checks handoff fields before a collection revision enters the ranking review.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "required = {\"name\", \"collection_revision\", \"owner\", \"refresh_policy\"}\n",
        "card = {\n",
        "    \"name\": \"cedar-docs\",\n",
        "    \"collection_revision\": \"cedar-docs-r12\",\n",
        "    \"owner\": \"Applied Foundations\",\n",
        "    \"refresh_policy\": \"weekly editorial snapshot\",\n",
        "}\n",
        "sorted(required - card.keys())\n"
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
