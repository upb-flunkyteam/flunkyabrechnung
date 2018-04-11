from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import *
from sqlalchemy import *

# Here are all sqlalchemy DBOs defined


Base = declarative_base()


class Player(Base):
    __tablename__ = "player"

    pid = Column(String, primary_key=True)
    firstname = Column(String, nullable=False)
    middlename = Column(String)
    lastname = Column(String, nullable=False)
    nickname = Column(String)
    address = Column(String)
    phone = Column(String)
    comment = Column(String)

    def __repr__(self):
        return " ".join(
            filter(None,
                   (self.firstname,
                    self.middlename,
                    "\"{}\"".format(self.nickname) if self.nickname else None,
                    self.lastname)))


class Tournament(Base):
    __tablename__ = "tournament"

    tid = Column(Integer, primary_key=True)
    number = Column(String)
    orderingcode = Column(String, nullable=True, unique=True)
    playerlist = relationship("PlayerTournament", uselist=True, backref="tournament")
    comment = Column(String)
    # Tournament date will be filled when the tally is evaluated
    date = Column(Date)


class PlayerTournament(Base):
    __tablename__ = "playertournament"

    pid = Column(String, ForeignKey("player.pid"), primary_key=True)
    tid = Column(Integer, ForeignKey("tournament.tid"), primary_key=True)


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
