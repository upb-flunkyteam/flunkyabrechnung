from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Player(Base):
    __tablename__ = "player"

    pid = Column(Integer, autoincrement=True, primary_key=True)
    firstname = Column(String, nullable=False)
    middlename = Column(String)
    lastname = Column(String, nullable=False)
    nickname = Column(String)
    address = Column(String)
    phone = Column(String)
    email = Column(String)
    comment = Column(String)

    def short_str(self):
        if self.nickname:
            return "\"{}\" {}".format(self.nickname, self.lastname)
        else:
            return " ".join(
                filter(None,
                       map(str, (self.firstname,
                                 self.middlename,
                                 self.lastname))))

    def __repr__(self):
        return " ".join(
            filter(None,
                   (self.firstname,
                    self.middlename,
                    "\"{}\"".format(self.nickname) if self.nickname else None,
                    self.lastname)))

    def __lt__(self, other):
        return str(self) < str(other)


class Tournament(Base):
    __tablename__ = "tournament"

    tid = Column(Integer, primary_key=True)
    ordercode = Column(String, ForeignKey("tournamentplayerlists.id"), default="")
    comment = Column(String)
    # Tournament date will be filled when the tally is evaluated
    date = Column(Date)

    def __repr__(self):
        return str(self.tid)

    def __lt__(self, other):
        return self.tid < other.tid


class TournamentPlayerLists(Base):
    __tablename__ = "tournamentplayerlists"

    id = Column(String, primary_key=True)
    pid = Column(Integer, ForeignKey("player.pid"), primary_key=True)


class Tallymarks(Base):
    __tablename__ = "tallymarks"

    pid = Column(String, ForeignKey("player.pid"), primary_key=True)
    tid = Column(Integer, ForeignKey("tournament.tid"), primary_key=True)
    beers = Column(Integer, nullable=False)
    last_modified = Column(DateTime, nullable=False)


class Account(Base):
    __tablename__ = "account"

    id = Column(Integer, autoincrement=True, primary_key=True)
    pid = Column(String, ForeignKey("player.pid"))
    deposit = Column(Numeric, nullable=False)
    comment = Column(String)
    date = Column(Date, nullable=False)
    last_modified = Column(DateTime, nullable=False)
