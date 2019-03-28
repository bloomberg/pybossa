"""
This module should not depend on either the app or the request context
"""
from itertools import chain
import logging

import numpy as np


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class NoAnswer(object):

    def __getitem__(self, key):
        return self

    def __iter__(self):
        while True:
            yield self

    def get(self, key, default=None, **kwargs):
        return self


class Answer(object):

    _no_ans = NoAnswer()

    def __init__(self, ans):
        self.ans = ans

    def __getitem__(self, key):
        return Answer(self.ans.get(key, self._no_ans))

    def __iter__(self):
        if isinstance(self.ans, list):
            base = self.ans
        else:
            base = []
        return (Answer(x) for x in chain(base, self._no_ans))


### Equalities


def equality(one, two):
    return one == two


### Statistics


class Statistic(object):

    def update(self, seen, true):
        self._update(seen.ans, true)
        return self

    def compute(self, taskrun, gold, path):
        compute(self, taskrun, gold, path)


class RightWrongCount(Statistic):

    compare_lists = False

    def __init__(self, right=0, wrong=0, compare_fn=equality):
        self.right = right
        self.wrong = wrong
        self.equal = compare_fn

    def _update(self, seen, true):
        if self.equal(seen, true):
            self.right += 1
        else:
            self.wrong += 1

    @property
    def value(self):
        return {
            'right': self.right,
            'wrong': self.wrong
        }


class ConfusionMatrix(Statistic):

    compare_lists = False

    def __init__(self, labels, matrix=None):
        self.labels = labels
        self.index = {v: i for i, v in enumerate(labels)}
        n = len(labels)
        if not matrix:
            self.matrix = np.zeros((n, n), dtype=int)
        else:
            self.matrix = np.array(matrix)

    def _update(self, seen, true):
        seen_ix = self.index.get(seen)
        if seen_ix is None:
            logger.warning('Invalid response label %s, won\'t update', seen)
            return
        true_ix = self.index.get(true)
        if true_ix is None:
            logger.warning('Invalid true label %s, won\'t update', true)
            return
        self.matrix[true_ix][seen_ix] += 1

    @property
    def value(self):
        return {
            'matrix': self.matrix.tolist()
        }


def compute(stat, taskrun, gold, path):
    return _compute(stat, Answer(taskrun), gold, path.split('.'))


def _compute(stat, taskrun, gold, path_parts):
    if isinstance(gold, list) and (path_parts or not stat.compare_lists):
        for ans, gold_ans in zip(taskrun, gold):
            _compute(stat, ans, gold_ans, path_parts)
        return stat

    if not path_parts:
        return stat.update(taskrun, gold)

    next_part = path_parts[0]
    other_parts = path_parts[1:]
    try:
        gold_ans = gold[next_part]
    except KeyError:
        return stat
    ans = taskrun[next_part]
    return _compute(stat, ans, gold_ans, other_parts)


def count_matches(taskrun, gold, path):
    stat = compute(RightWrongCount(), taskrun, gold, path)
    return stat.right, stat.wrong
