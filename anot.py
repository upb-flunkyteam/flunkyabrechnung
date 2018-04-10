def printio(f):
    def _printio(*args):
        result = f(*args)
        print(args, "->", result)
        return result

    return _printio