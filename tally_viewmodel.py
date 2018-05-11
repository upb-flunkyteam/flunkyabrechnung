'''
sanetize list
fill up nonzero ordercodes from tournament table
process (existing ones (the ones where tid in tallymarks))
process (new ones)
'''
from dbo import *
from itertools import *
from math import ceil
from input_funcs import get_tallymarks
from datetime import datetime, date
import cmd


class TallyVM:
    def __init__(self, session, config, controller):
        self.session = session
        self.config = config
        self.controller = controller

    def main(self, turnierseq: list):
        if not turnierseq:
            turnierseq = [(tid, None) for tid in
                          chain.from_iterable(
                              self.session.query(Tournament.tid).filter(
                                  Tournament.date == None).all())]

        # split sequences in: existing turniers with dates, existing turniers, not existing turniers
        # sort existing turniers with date by date
        turniers = dict(turnierseq)
        if not turniers:
            # TODO if there are unfilled tallys we can assume,
            # TODO that the user wanted to fill the lists with the same ordercode
            print("No Turniers Provided. Provide a list of tournaments")
            return

        self.augment_turnierseq(turniers)

        # concatenate existing turniers with date and without date
        provided_turniers = set(turniers.keys())
        existing_turniers = set(chain.from_iterable(self.session.query(Tournament.tid).all()))

        existing_provided_turiers = provided_turniers.intersection(existing_turniers)

        # split sequences in: existing turniers with dates, existing turniers, not existing turniers
        # sort existing turniers with date by date
        existing_provided_turiers_wdate = list(
            filter(lambda tid: tid in provided_turniers, chain.from_iterable(self.session.query(
                Tournament.tid).filter(Tournament.date != None).order_by(Tournament.date).all())))

        # create Tournament for non existing turniers
        non_existing_provided_turniers = provided_turniers - existing_provided_turiers
        self.session.add_all([Tournament(tid=n) for n in non_existing_provided_turniers])
        self.session.commit()
        # sort existing without date turniers by number
        existing_provided_turiers_wodate = list(sorted(provided_turniers - set(existing_provided_turiers_wdate)))

        self.input_marks([(tid, turniers[tid]) for tid in existing_provided_turiers_wdate])

        self.input_marks([(tid, turniers[tid]) for tid in existing_provided_turiers_wodate])

    def input_marks(self, turniers: list):
        '''
        process()
            group by ordercode
            split groups with maxgroupsize
            for all players in ordercode
                input
            until ctrl+d hit twice:
                add single inputs
        '''
        for k, g in groupby(turniers, key=lambda x: x[1]):
            players = self.session.query(Player).join(TournamentPlayerLists).filter(TournamentPlayerLists.id == k).all()
            # this calculation will split in nearly even groups
            g = list(g)
            n, max = len(g), self.config.getint("tally", "max_groupsize")
            n_splits = int(ceil(n / max))
            splitsize = int(ceil(max * (n / max) / n_splits))
            for split in range(n_splits):
                chunk = list(map(lambda x: x[0], g[split * splitsize:(split + 1) * splitsize]))
                self.insert_grouped_tally(chunk, players)
                for tid in chunk:
                    print("filling chunk individually: {}".format(tid))

                    InputShell(self.controller, tid).cmdloop()
                    self.session.query(Tournament).filter(Tournament.tid == tid).first().date = date.today()
                    self.session.commit()

    def insert_grouped_tally(self, tally_ids: list, players: list):
        print("Filling:", "\t".join(map(str, tally_ids)))
        marks = []
        while True:
            try:
                for player in players[len(marks):]:
                    marks.append(get_tallymarks(len(tally_ids), "{}: ".format(repr(player))))
                break
            except EOFError:
                if marks:
                    print("\033[F" + 80 * " ", end="")
                    marks.pop()
        for i, tid in enumerate(tally_ids):
            for j, player in enumerate(players):
                self.session.merge(Tallymarks(pid=player.pid, tid=tid, beers=marks[j][i], last_modified=datetime.now()))
        self.session.commit()

    def augment_turnierseq(self, turniers: dict):
        '''
        Gets the ordercode from database and fills the given dictionary
        :param turniers:
        :return:
        '''
        for turnier, ordercode in turniers.items():
            if ordercode is None:
                code = self.session.query(Tournament.ordercode).filter(Tournament.tid == turnier).first()
                turniers[turnier] = 0 if code is None or not code[0] else code[0]


class InputShell(cmd.Cmd):
    def __init__(self, commander, tid):
        super().__init__()
        self.commander = commander  # type: CommandProvider
        self.tid = tid

    intro = 'Type one of the following commands: input, newplayer, deposit\n' \
            'Press Ctrl+D to finish current command'
    prompt = '\r                                \r> '

    def do_newplayer(self, arg):
        'create new player'
        self.commander.addplayers()

    def do_input(self, arg):
        'input stuff for players'
        marks = dict()
        try:
            while True:
                player = self.commander.get_user()
                marks[player] = get_tallymarks(1, "{} marks:       ".format(str(player)))[0]
        except EOFError:
            for player, beers in marks.items():
                self.commander.session.merge(
                    Tallymarks(pid=player.pid, tid=self.tid, beers=beers,
                               last_modified=datetime.now()))
        self.commander.session.commit()

    def do_deposit(self, arg):
        """input stuff for players"""
        self.commander.deposit()

    def onecmd(self, line):
        # when ctrl+d is pressed we exit the shell
        if line == "EOF":
            return True
        super().onecmd(line)

    def do_quit(self, arg):
        """quit stuff"""
        return True
