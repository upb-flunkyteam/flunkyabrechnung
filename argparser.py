# Custom validator:  https://docs.python.org/3/library/argparse.html#type

import argparse

# TODO improve documentation
# TODO validator for turnier sequnces
# TODO specific validator for create tally

class OrderedAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if not 'commands' in namespace:
            setattr(namespace, 'commands', [])
        previous = namespace.commands
        previous.append((self.dest, values))
        setattr(namespace, 'commands', previous)


class TrueOrderedAction(OrderedAction):
    def __call__(self, parser, namespace, values, option_string=None):
        OrderedAction.__call__(self, parser, namespace, True, option_string=None)


parser = argparse.ArgumentParser(description="Commands can be placed in any order")
parser.add_argument('--verbose', '-v', action='count')
cmds = parser.add_argument_group("commands")
cmds.add_argument("--tally", metavar="<turnier seq>", nargs="?", help="tally help", action=OrderedAction)
cmds.add_argument("--deposit", help="deposit help", action=TrueOrderedAction, nargs=0)
cmds.add_argument("--billing", nargs="?", metavar="<filename>",
                  help="if no filename provided, the billing will be printed to stdout", action=OrderedAction)
cmds.add_argument("--transfer", help="transfer money from player to set of players", action=TrueOrderedAction, nargs=0)
cmds.add_argument("--createtally", metavar=("<turnier seq>", "{asta, local, None}"), nargs="*", help="create tally",
                  action=OrderedAction)
cmds.add_argument("--addplayers", help="will ask you to provide new players", action=TrueOrderedAction, nargs=0)

def getargs(args = None):
    return parser.parse_args(args)
