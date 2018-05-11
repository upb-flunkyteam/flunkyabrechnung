import re
from anot import printio
from logging import *
from copy import copy


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
            matches = list(filter(
                lambda player: not text or str(player).lower().startswith(text.lower()), self.options))
            self.cache[text] = [Result(i + 1, s) for i, s in enumerate(matches)]
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


class Result:
    def __init__(self, n, player):
        self.n = n
        self.player = player

    def __repr__(self):
        pre = "{}) ".format(self.n) if self.n else ""
        return pre + repr(self.player)
