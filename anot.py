def printio(f):
    def _printio(*args):
        result = f(*args)
        print(f.__name__ + str(args), "->", str(result) + "\n")
        return result

    return _printio
