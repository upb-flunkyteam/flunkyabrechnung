from datetime import date


def create_tally_latex_code(number: int, date: date, code: str, players: list,otherdeptors:list,
                            responsible: list = ()) -> str:
    date = "$ \square\,$%(date)s\enskip $ \square\, $" % \
           {"date": date.strftime("%d.%m.%Y")} if date else ""
    return r"""
    \fancyfoot[C]{\tiny %(otherdeptors)s}
    \hdr{%(n)d}[%(date)s][%(code)s][%(responsible)s]
\begin{multicols}{2}
\foreach \player in {%(players)s}{
    \listitem{\player}
}
\pgfmathparse{40-%(len)d}
\foreach \dummy in {1,...,\pgfmathresult}{
    \listitem{}
}
\bracketedText{Neuflunker}{\foreach \dummy in {1,...,4}{
    \newplayeritem
}}
\bracketedText{Einmalflunker\\\tiny Vorbezahlte Biere umrahmen}{
\foreach \dummy in {1,...,4}{
    \temporaryplayeritem
}}
\end{multicols}\vspace{-1em}
\newpage
""" % {"n": number, "date": date, "code": code, "players": ", ".join(players), "otherdeptors": ", ".join(otherdeptors),
       "len": len(players),
       "responsible": "".join([r"$ \square $ & %(name)s\\" % {"name": name}
                               for name in responsible]) + "$ \square $" if responsible else ""}

