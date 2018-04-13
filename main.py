from argparser import ArgumentParser
from configparser import ConfigParser
import os
from commands import *
from logging import *

if __name__ == "__main__":
    # Load config
    config = ConfigParser()
    config.read("main.conf")
    # TODO validate that all entries in the config are actually given

    # Create SQLalchemy engine (initialize vars and so on)
    os.makedirs(os.path.dirname(config["DEFAULT"]["dbpath"]), exist_ok=True)
    engine = create_engine("sqlite:///" + config["DEFAULT"]["dbpath"])
    Base.metadata.create_all(engine)
    sess = Session(bind=engine)

    # Load argparser get arguments
    argparser = ArgumentParser(sess, config)
    args = argparser.getargs()
    getLogger().setLevel(30 - 10 * (args.verbose or 0))
    commands = args.commands

    # call commands one by one
    command_provider = CommandProvider(sess, config)
    for cmd, arg in commands:
        debug("Executing \"{}\" with args: {}".format(cmd, arg))
        func = getattr(command_provider, cmd)
        if not isinstance(arg,bool):
            func(*arg)
        else:
            func()
