import argparse
import sys
import re
from dbo import *
from functools import partial
from itertools import chain
from logging import *


# TODO improve documentation

class ArgumentParser:
    def __init__(self, session, config):
        self.session = session
        self.config = config

        self.parser = argparse.ArgumentParser(
            description="Commands are executed in the following order: " + config.get("DEFAULT", "command_order")
            ,
            epilog="<turnier seq>: comma list of <ranges>[:[<code>]], "
                   "a <range> is eigher a integer scalar or a integer range (2-40), "
                   "a <code> is a 6 character case insensitive code for the list ordering or 0. "
                   "if an empty or 0 ordercode is provided, the playerlist will not be used when inserting tallies, non empty ordercodes override the internal ordercode for the tally\n"
                   "\n\n"
                   "ctrl-d will revert the last input or stop the current input loop.\n"
                   "If you stopped the current input loop, press ctrl-d again to delete the last entry\n")
        self.parser.add_argument('--verbose', '-v', action='count')
        cmds = self.parser.add_argument_group("commands")
        cmds.add_argument("--tally", default=argparse.SUPPRESS, metavar="<turnier seq>", nargs="?", help="tally help",
                          type=self.turnierseq_type)
        cmds.add_argument("--deposit", default=argparse.SUPPRESS, help="deposit help", action="store_true")
        cmds.add_argument("--billing", default=argparse.SUPPRESS, help="calculate and print balance for all users",
                          action="store_true")
        cmds.add_argument("--transfer", default=argparse.SUPPRESS, help="transfer money from player to set of players",
                          action="store_true")
        # cmds.add_argument("--createtally", metavar="<turnier seq>", nargs="?",
        #                   type=partial(self.turnierseq_type, createtally=True),
        #                   help="Creates a sequence of empty tallys in database. If no parameter given,"
        #                        " it will try to automatically create the amount configured in main.conf")
        cmds.add_argument("--printtally", default=argparse.SUPPRESS, choices=["asta", "local", "None"],
                          help="It will print all not yet printed tallys. The parameter selects how to print, if at all.")
        cmds.add_argument("--addplayers", default=argparse.SUPPRESS, help="will ask you to provide new players",
                          action="store_true")

    def turnierseq_type(self, turnierseq: str, createtally=False) -> list:
        # this will be converted in a list tuples of turnier ids and ordercodes

        # validate syntax
        intervall = r"(?:\d+|\d+-\d+)(?:|:|:0|:\w{6})"
        if re.fullmatch(intervall + "(?:," + intervall + ")*", turnierseq) is None:
            raise argparse.ArgumentTypeError("provided turnier sequence has wrong syntax")

        seq = turnierseq.split(",")
        numbers = dict()
        for elem in seq:
            # if ordercode missing it will be set to None
            intervall, code = (elem.split(":") + [None])[:2]

            try:
                numbers[int(intervall)] = code
            except ValueError:
                match = re.fullmatch(r"(?P<start>\d+)-(?P<end>\d+)", intervall)
                # no need to validate, if the can convert to int, if end > start, its simply empty
                numbers.update(dict([(i, code) for i in range(int(match.group("start")), int(match.group("end")) + 1)]))
        return list(numbers.items())

    def getargs(self):
        args = sys.argv[1:] or self.config.get("DEFAULT", "defaultcommand").split() or ["-h"]

        return self.parser.parse_args(args)
