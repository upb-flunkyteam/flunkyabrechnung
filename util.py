def sortedplayers(players, idx: int = None):
    if idx is None:
        return sorted(players, key=lambda p: "".join(filter(lambda ch: ch.isalnum(), p.short_str())))
    else:
        # if a index is given, the player list contains tuples, where the actual player is stored at index "idx"
        return sorted(players, key=lambda p: "".join(filter(lambda ch: ch.isalnum(), p[idx].short_str())))
