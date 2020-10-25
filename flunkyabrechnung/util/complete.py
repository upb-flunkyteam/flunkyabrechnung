import re
from copy import copy
from itertools import permutations
from math import *


class Completer(object):
    # Custom completer

    def __init__(self, options):
        self.options = sorted(options, key=lambda p: p.pid)
        self.cache = dict()
        self.lasttext = None

    def get_matches(self, text):
        text = str(text)
        match = re.fullmatch("(?:{}|)(\d+)\s?(?:\)|\.|)".format(self.lasttext), text)
        if match:
            # text is a number, therefore we have to retrieve the number of the last match
            try:
                if self.lasttext is None:
                    return []
                return [self.get_matches(self.lasttext)[int(match[1]) - 1]]
            except IndexError:
                # out of bounds
                return []
        if text not in self.cache:
            matches = list(
                filter(lambda player: not text or is_valid_prefix_of(text.lower(), player.plain_str()), self.options))
            self.cache[text] = [Result(i + 1, s, int(ceil(log10(len(matches))))) for i, s in enumerate(matches)]
            self.lasttext = text
        return self.cache[text]

    def complete(self, text, state):
        # return match indexed by state
        try:
            return self.get_matches(text)[state]
        except IndexError:
            return None

    def complete_str(self, text, state):
        result = self.complete(text, state)
        if result and state == 0 and self.complete(text, 1) is None:
            # we can complete
            # we need to save this as a prefix, so that we can retrieve the player
            result = copy(result)
            result.n = None
            self.cache[repr(result)] = [self.complete(text, 0)]
        return repr(result) if result else None


def is_valid_prefix_of(prefix, full_match):
    S, T = prefix.split(), full_match.split()
    # two sets S and T

    if len(S) > len(T):
        # prune
        return False
    # every element of s is prefix of a t in T.
    for perm in permutations(T, len(S)):
        if all(map(lambda i: perm[i].startswith(S[i]), range(len(S)))):
            return True
    return False


class Result:
    def __init__(self, n, player, min_digits=1):
        self.n = n
        self.min_digits = min_digits
        self.player = player

    def __repr__(self):
        pre = ("{:0" + str(self.min_digits) + "}) ").format(self.n) if self.n else ""
        return pre + repr(self.player)
