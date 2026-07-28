```ipynb
{
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "# ORCHID-CKD-202 interim analysis workbook\n",
        "\n",
        "Operational notebook for checking the completeness of the July 2026 interim analysis extract. The working table uses de-identified participant keys only."
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "import pandas as pd\n",
        "\n",
        "study = 'ORCHID-CKD-202'\n",
        "extract_date = pd.Timestamp('2026-07-21')\n",
        "records = [\n",
        "    {'participant_key': 'B02-001', 'visit_state': 'complete', 'lab_review': 'complete', 'query_state': 'closed'},\n",
        "    {'participant_key': 'B02-002', 'visit_state': 'complete', 'lab_review': 'complete', 'query_state': 'open'},\n",
        "    {'participant_key': 'B02-003', 'visit_state': 'pending', 'lab_review': 'not_due', 'query_state': 'not_applicable'},\n",
        "]\n",
        "analysis_frame = pd.DataFrame.from_records(records)\n",
        "analysis_frame\n"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": null,
      "metadata": {},
      "outputs": [],
      "source": [
        "def readiness_summary(frame: pd.DataFrame) -> pd.DataFrame:\n",
        "    expected = {'visit_state': 'complete', 'lab_review': 'complete'}\n",
        "    ready = (frame[list(expected)] == pd.Series(expected)).all(axis=1) & (frame['query_state'] != 'open')\n",
        "    return pd.DataFrame({\n",
        "        'study': [study],\n",
        "        'extract_date': [extract_date.date().isoformat()],\n",
        "        'records_reviewed': [len(frame)],\n",
        "        'records_ready': [int(ready.sum())],\n",
        "        'records_needing_follow_up': [int((~ready).sum())],\n",
        "    })\n",
        "\n",
        "readiness_summary(analysis_frame)\n"
      ]
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": [
        "## Review boundaries\n",
        "\n",
        "This workbook supports operational readiness only. Protocol interpretation, medical assessment, and final statistical programming remain under their approved procedures."
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
      "version": "3.11"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5
}
```
