# Import Library
import pandas as pd
import numpy as np
import os
import glob
import datetime as dt
import uuid
from operator import itemgetter

# Import Local Library
from common.access_db.database import Database
import finance.config as config
from stock_price_api import StockPriceApi


class LoadTransaction:
    def __init__(self):
        self.db = Database(config.db_source)
        self.file_path = config.source_file_path
        self.file_name = config.source_file_name
        self.target_path = config.target_path

    def get_latest_transaction(self) -> pd.DataFrame:
        file = self.get_latest_file()
        if not file:
            raise Exception("Transaction file not available")
        df = pd.read_csv(file)
        df.rename(config.column_mapping, inplace=True, axis=1)
        return df

    def get_latest_file(self) -> list:
        files = []
        all_files = glob.glob(self.file_path + '/' + self.file_name)
        for file in all_files:
            mdt = dt.datetime.utcfromtimestamp(os.stat(file).st_mtime)
            files.append({'file_name': file, 'md_time': mdt})
        return sorted(files, key=itemgetter('md_time'), reverse=True)[0]['file_name'] if len(files) > 0 else []

    def check_target_file(self, file_name, df_columns):
        if os.path.isfile(self.target_path + '/' + file_name):
            target_df = pd.read_excel(self.target_path + '/' + file_name)
        else:
            target_df = pd.DataFrame(columns=df_columns)
        return target_df

    def merge_transaction(self, source_df) -> pd.DataFrame:
        eqd_trans_df = self.check_target_file('EquityTransaction.xlsx', config.column_mapping.values())
        new_rec_df = pd.merge(eqd_trans_df, source_df, how='outer', indicator=True).query('_merge=="right_only"').drop(
            ['_merge'], axis=1)
        return pd.concat([eqd_trans_df, new_rec_df])

    def populate_position(self, instruments, transaction_df):
        position_df = self.check_target_file('Position.xlsx', config.position_columns)
        for instrument in instruments:
            df = transaction_df[transaction_df['Symbol'] == instrument]
            df.sort_values('OrderExecTime')
            for index, row in df.iterrows():
                if row['TradeType'] == 'buy':
                    buy_row = pd.DataFrame({
                        'Symbol': [row['Symbol']],
                        'Quantity': [row['Quantity']],
                        'BuyDate': [row['TradeDate']],
                        'BuyTime': [row['OrderExecTime']],
                        'BuyPrice': [row['Price']]
                    })
                    position_df = pd.concat([position_df, buy_row], ignore_index=True)

                    print(position_df)
                if row['TradeType'] == 'sell':
                    idx = position_df[(position_df['SellDate'].isna()) & (
                                    position_df['BuyTime'] == position_df['BuyTime'].min())].index.values.astype(int)[0]
                    dict = {
                        'Symbol': row['Symbol'],
                        'Quantity': row['Quantity'],
                        'BuyDate': row['TradeDate'],
                        'BuyPrice': row['Price']
                    }
                    position_df.append(dict, ignore_index=True)

    def process_transaction(self):
        source_df = self.get_latest_transaction()
        transaction_df = self.merge_transaction(source_df)
        instruments = transaction_df.Symbol.unique()
        ratio_df = StockPriceApi(instruments).instrument_ratios()
        self.populate_position(instruments, transaction_df)
        print(ratio_df)


a = LoadTransaction()
a.process_transaction()
