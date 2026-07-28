```ipynb
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# 2026.07 release reconciliation notes\n",
    "\n",
    "Hummingbird Payments の Orchid Ledger リリース後に、Ledger Platform が残した照合メモ。公開前の集計値ではなく、日次差分の傾向だけを確認する。"
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
    "states = [\"posted\", \"posted\", \"reversed\", \"posted\", \"held\"]\n",
    "Counter(states)\n"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "集計は監査対象の元帳へ書き戻さず、レビュー用のローカル検算として扱う。Poppy Gateway 側の再送は別の週次確認に分けた。"
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
