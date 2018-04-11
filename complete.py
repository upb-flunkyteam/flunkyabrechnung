from collections import OrderedDict
import re
from anot import printio


class LRU_cache(OrderedDict):
    'Store items in the order the keys were last added'

    def __init__(self, n, *args, **kwds):
        super().__init__(*args, **kwds)
        self.maxsize = n

    def __setitem__(self, key, value):
        if key in self:
            del self[key]
        if len(self) == self.maxsize:
            self.popitem()
        OrderedDict.__setitem__(self, key, value)


class Completer(object):
    # Custom completer

    def __init__(self, options):
        self.options = sorted(options, key=lambda p: p.pid)
        self.cache = LRU_cache(1000)
        self.lasttext = None

    def get_matches(self, text):
        match = re.fullmatch("(\d+)\s?(?:\)|\.|)", text)
        if match:
            # text is a number, therefore we have to retrieve the number of the last match
            try:
                return (self.get_matches(self.lasttext)[int(match[1]) - 1],)
            except IndexError:
                # out of bounds
                return []
        if text not in self.cache:
            matches = list(filter(
                lambda s: not text or s.pid.lower().startswith(text.lower()), self.options))
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
            result.n = None
            self.cache[repr(result)] = [self.complete(text, 0)]
        return repr(result) if result else None


class Result:
    def __init__(self, n, player):
        self.n = n
        self.player = player

    def __repr__(self):
        pre = "{}) ".format(self.n) if self.n else ""
        return pre + "{} ({})".format(self.player.pid, repr(self.player))
