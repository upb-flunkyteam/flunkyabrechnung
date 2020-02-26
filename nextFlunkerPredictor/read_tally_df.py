import pandas as pd
from sqlalchemy import create_engine

engine = create_engine('sqlite:///flunky.db')
with engine.connect() as conn, conn.begin():
    data = pd.read_sql_table('tallymarks', conn)
print(data.describe())
data.to_csv('tally.csv')