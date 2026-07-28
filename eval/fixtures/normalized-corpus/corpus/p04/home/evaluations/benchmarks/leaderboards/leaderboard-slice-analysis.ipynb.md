```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# Leaderboard slice analysis\n",
        "\n",
        "Inspects whether a Cedar metric shift is concentrated in a particular editorial slice.\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "rows = [\n",
        "    {\"slice\": \"short-factual\", \"package\": \"model-alpha\", \"value\": 0.792},\n",
        "    {\"slice\": \"short-factual\", \"package\": \"model-beta\", \"value\": 0.771},\n",
        "    {\"slice\": \"long-technical\", \"package\": \"model-alpha\", \"value\": 0.748},\n",
        "    {\"slice\": \"long-technical\", \"package\": \"model-beta\", \"value\": 0.731},\n",
        "]\n",
        "{row[\"slice\"] for row in rows}\n"
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
