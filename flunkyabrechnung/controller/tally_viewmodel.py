'''
sanitize list
fill up nonzero ordercodes from tournament table
process (existing ones (the ones where tid in tallymarks))
process (new ones)
'''
import cmd
import readline
from itertools import *
from math import ceil

from flunkyabrechnung.model import *
from flunkyabrechnung.util import *


class TallyVM:
    def __init__(self, db, config, controller):
        self.db = db
        self.config = config
        self.controller = controller

    def main(self, turnierseq: list):
        if not turnierseq:
            turnierseq = [(tid, None) for tid in
                          chain.from_iterable(
                              self.db.query(Tournament.tid).filter(
                                  Tournament.date == None).all())]

        # split sequences in: existing turniers with dates, existing turniers, not existing turniers
        # sort existing turniers with date by date
        turniers = dict(turnierseq)
        if not turniers:
            print("No Turniers Provided and no turniers that are not yet in the database. "
                  "Provide a list of tournaments you want to edit")
            return

        self.augment_turnierseq(turniers)

        # concatenate existing turniers with date and without date
        provided_turniers = set(turniers.keys())
        existing_turniers = set(chain.from_iterable(self.db.query(Tournament.tid).all()))

        existing_provided_turiers = provided_turniers.intersection(existing_turniers)

        # split sequences in: existing turniers with dates, existing turniers, not existing turniers
        # sort existing turniers with date by date
        existing_provided_turiers_wdate = list(
            filter(lambda tid: tid in provided_turniers, chain.from_iterable(self.db.query(
                Tournament.tid).filter(Tournament.date != None).order_by(Tournament.date).all())))

        # create Tournament for non existing turniers
        non_existing_provided_turniers = provided_turniers - existing_provided_turiers
        self.db.add_all([Tournament(tid=n) for n in non_existing_provided_turniers])
        self.db.flush()
        # sort existing without date turniers by number
        existing_provided_turiers_wodate = list(sorted(provided_turniers - set(existing_provided_turiers_wdate)))

        self.input_marks([(tid, turniers[tid]) for tid in existing_provided_turiers_wdate], existing=True)

        self.input_marks([(tid, turniers[tid]) for tid in existing_provided_turiers_wodate])

    def augment_turnierseq(self, turniers: dict):
        '''
        Gets the ordercode from database and fills the given dictionary
        :param turniers:
        :return:
        '''
        for turnier, ordercode in turniers.items():
            if ordercode is None:
                code = self.db.query(Tournament.ordercode).filter(Tournament.tid == turnier).first()
                turniers[turnier] = 0 if code is None or not code[0] else code[0]

    def input_marks(self, turniers: list, existing=False):
        '''
        process()
            group by ordercode
            split groups with maxgroupsize
            for all players in ordercode
                input
            until ctrl+d hit twice:
                add single inputs
        '''
        print("\nProcessing the following tallies:")

        for ordercode, g in groupby(turniers, key=lambda x: x[1]):
            players = self.db.query(Player).join(TournamentPlayerLists).filter(
                TournamentPlayerLists.id.like(f"%{ordercode}%")).all()
            # this calculation will split in nearly even groups
            g = list(g)
            n, max = len(g), self.config.getint("tally", "max_groupsize")
            n_splits = int(ceil(n / max))
            splitsize = int(ceil(max * (n / max) / n_splits))
            for split in range(n_splits):
                chunk = list(map(lambda x: x[0], g[split * splitsize:(split + 1) * splitsize]))
                self.insert_grouped_tally(chunk, players, ordercode)
                for tid in chunk:
                    date = self.controller.predict_or_retrieve_tournament_date(tid)
                    print(f"\n\nProcessing tally {tid} (date {date.strftime('%d.%m.%Y')}) individually")

                    # We assume the tid date to be set by insert_grouped_tally()
                    InputShell(self.controller, tid, date).cmdloop()
                    self.db.commit()

    def insert_grouped_tally(self, tally_ids: list, players: list, ordercode):
        debug("insert grouped tally entered")
        self.verify_dates(tally_ids)

        print("\nProcessing: {}".format(
            "\t".join(map(str, tally_ids))) + f"\t\t(ordercode: {ordercode.title()})" if ordercode else "")
        sorted_players = sortedplayers(players)
        marks = []
        while True:
            try:
                for player in sorted_players[len(marks):]:
                    beers = [t.beers for t in self.db.query(Tallymarks).filter(
                        Tallymarks.pid == player.pid, Tallymarks.tid.in_(tally_ids)).all()]
                    marks.append(get_tallymarks(len(tally_ids), beers, "{}: ".format(str(player))))
                    for i, tid in enumerate(tally_ids):
                        beers = marks[-1][i]
                        self.controller.update_beers(beers, player, tid)
                # all players are processed, so we can exit the loop
                break
            except EOFError:
                debug("insertgrouped tally reset by Ctrl+D")
                if marks:
                    print("\033[F" + 80 * " ", end="")
                    marks.pop()

        debug("insert grouped tally exit")

    def verify_dates(self, tally_ids):
        dates = [self.controller.predict_or_retrieve_tournament_date(tid) for tid in tally_ids]
        print("Tournament{}:".format("s" if len(tally_ids) > 1 else ""), "\t".join(
            map(lambda tid_date: "{} (on {})".format(tid_date[0], tid_date[1].strftime("%d.%m.%Y")),
                zip(tally_ids, dates))))

        tids = get_tournaments("Provide tournament numbers with wrong date, if any: ", max(tally_ids))

        if tids:
            tids_with_wrong_dates = tids.intersection(tally_ids)
        else:
            for tid, date in zip(tally_ids, dates):
                self.db.merge(Tournament(tid=tid, date=date))
                self.db.flush()
            return

        print("Press <ENTER> or <TAB> to insert predicted date. Ctrl + D to revert")

        if tids_with_wrong_dates:
            tids_with_wrong_dates = tuple(sorted(tids_with_wrong_dates))
            i = 0
            old_completer = readline.get_completer()
            while i < len(tids_with_wrong_dates):
                try:
                    tid = tids_with_wrong_dates[i]
                    readline.set_completer(
                        lambda text, state:
                        self.controller.predict_or_retrieve_tournament_date(tid).strftime("%d.%m.%Y")
                        if state == 0 else None)
                    readline.parse_and_bind('tab: complete')
                    date = get_date("Date for {}: ".format(tid),
                                    default=self.controller.predict_or_retrieve_tournament_date(tid))
                    self.db.merge(Tournament(tid=tid, date=date))
                    self.db.flush()
                    i += 1
                except EOFError:
                    print("\033[F" + 80 * " ", end="")
                    i -= 1
            readline.set_completer(old_completer)
        else:
            print("Your turnier ids didn't match, so it is assumed that all dates where correct!")
            return dates


class InputShell(cmd.Cmd):
    def __init__(self, commander, tid, date):
        super().__init__()
        self.commander = commander  # type: CommandProvider
        self.tid = tid
        self.date = date

    intro = 'Type one of the following commands: addplayer, input, payment, transfer, gettally\n' \
            'Press Ctrl+D to finish current command'
    prompt = '\r                                \r> '

    def do_addplayer(self, arg):
        'create new player'
        self.commander.addplayers()

    def do_gettally(self, arg):
        self.commander.gettally([(self.tid, None)])

    def do_transfer(self, arg):
        self.commander.transfer([(self.tid, None)])

    def do_input(self, arg):
        'input stuff for players'
        try:
            while True:
                player = self.commander.get_user()
                old_entry = self.commander.db.query(Tallymarks).filter(
                    Tallymarks.pid == player.pid, Tallymarks.tid == self.tid).first()
                beers = old_entry.beers if old_entry else 0
                marks = get_tallymarks(1, beers, "{} marks:       ".format(str(player)))[0]
                self.commander.update_beers(marks, player, self.tid)
        except EOFError:
            pass

    def do_payment(self, arg):
        """input stuff for players"""
        self.commander.payment(self.date)

    def onecmd(self, line):
        # when ctrl+d is pressed we exit the shell
        if line == "EOF":
            return True
        super().onecmd(line)

    def do_quit(self, arg):
        """quit stuff"""
        return True
