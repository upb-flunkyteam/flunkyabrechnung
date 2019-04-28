from datetime import date


def create_tally_latex_code(number: int, date: date, code: str, players: list,
                            responsible: list = ()) -> str:
    date = "$ \square\,$%(date)s\enskip $ \square\, $" % \
           {"date": date.strftime("%d.%m.%Y")} if date else ""

    return r"""\hdr{%(n)d}[%(date)s][%(code)s][%(responsible)s]
\begin{multicols}{2}
\foreach \player in {%(players)s}{
    \listitem{\player}
}
\pgfmathparse{52-%(len)d}
\foreach \dummy in {1,...,\pgfmathresult}{
    \listitem{}
}
\end{multicols}\newpage
""" % {"n": number, "date": date, "code": code, "players": ", ".join(players),
       "len": len(players),
       "responsible": "".join([r"$ \square $ & %(name)s\\" % {"name": name}
                               for name in responsible]) + "$ \square $" if responsible else ""}
