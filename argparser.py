import argparse
import sys
import re
from dbo import *
from functools import partial
from itertools import chain
from logging import *


# TODO improve documentation

class OrderedAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        # create or append command
        current = getattr(namespace, "commands", [])
        if values == True:
            namespace.commands = current + [(self.dest, [])]
        else:
            namespace.commands = current + [(self.dest, [values])]


class TrueOrderedAction(OrderedAction):
    def __call__(self, parser, namespace, values, option_string=None):
        OrderedAction.__call__(self, parser, namespace, True, option_string=None)


class ArgumentParser:
    def __init__(self, session, config):
        self.session = session
        self.config = config

        self.parser = argparse.ArgumentParser(
            description="Commands can be placed in any order",
            epilog="<turnier seq>: comma list of <ranges>[:[<code>]], "
                   "a <range> is eigher a integer scalar or a integer range (2-40), "
                   "a <code> is a 6 character case insensitive code for the list ordering or 0. "
                   "if an empty or 0 ordercode is provided, the playerlist will not be used when inserting tallies, non empty ordercodes override the internal ordercode for the tally\n"
                   "\n\n"
                   "ctrl-d will revert the last input or stop the current input loop.\n"
                   "If you stopped the current input loop, press ctrl-d again to delete the last entry\n")
        self.parser.add_argument('--verbose', '-v', action='count')
        cmds = self.parser.add_argument_group("commands")
        cmds.add_argument("--tally", metavar="<turnier seq>", nargs="?", help="tally help", type=self.turnierseq_type,
                          action=OrderedAction)
        cmds.add_argument("--deposit", help="deposit help", action=TrueOrderedAction, nargs=0)
        cmds.add_argument("--billing", nargs=0,
                          help="calculate and print balance for all users", action=TrueOrderedAction)
        cmds.add_argument("--transfer", help="transfer money from player to set of players", action=TrueOrderedAction,
                          nargs=0)
        cmds.add_argument("--createtally", metavar="<turnier seq>", nargs="?",
                          type=partial(self.turnierseq_type, createtally=True),
                          help="Creates a sequence of empty tallys in database. If no parameter given,"
                               " it will try to automatically create the amount configured in main.conf",
                          action=OrderedAction)
        cmds.add_argument("--printtally", choices=["asta", "local", "None"],
                          help="It will print all not yet printed tallys. The parameter selects how to print, if at all.",
                          action=OrderedAction)
        cmds.add_argument("--addplayers", help="will ask you to provide new players", action=TrueOrderedAction, nargs=0)

    def turnierseq_type(self, turnierseq: str, createtally=False) -> list:
        # this will be converted in a list tuples of turnier ids and ordercodes

        # validate syntax
        intervall = r"(?:\d+|\d+-\d+)(?:|:|:0|:\w{6})"
        if re.fullmatch(intervall + "(?:," + intervall + ")*", turnierseq) is None:
            raise argparse.ArgumentTypeError("provided turnier sequence has wrong syntax")

        seq = turnierseq.split(",")
        numbers = dict()
        for elem in seq:
            # if code missing it will be set to empty string
            intervall, code = (elem.split(":") + [None])[:2]

            try:
                numbers[int(intervall)] = code
            except ValueError:
                match = re.fullmatch(r"(?P<start>\d+)-(?P<end>\d+)", intervall)
                # no need to validate, if the can convert to int, if end > start, its simply empty
                numbers.update(dict([(i, code) for i in
                                     range(int(match.group("start")), int(match.group("end")))]))

        provided_turniers = set(numbers.keys())
        existing_turniers = set(chain.from_iterable(self.session.query(Tournament.tid).all()))

        existing_provided_turiers = provided_turniers.intersection(existing_turniers)
        if createtally:
            # print warning for all turniers, that already exist and ignore them
            if existing_provided_turiers:
                warning(
                    "ignoring the following turniers, because they exist already: "
                    + str(sorted(existing_provided_turiers)))
                for k in existing_provided_turiers:
                    numbers.pop(k)
            return list(numbers.items())
        else:
            # tally
            return list(numbers.items())

    def getargs(self):
        args = sys.argv[1:] or self.config.get("DEFAULT", "defaultcommand").split()

        return self.parser.parse_args(args)
