import math
import time
import traceback
from datetime import datetime, time as d_time

import Utils as util
from pytz import timezone

ORDER_TAG = 'BN_STRADDLE'
SPOT = 'NSE:NIFTY BANK'
LOTS = 20


def place_buy_sell_order(instruments, transaction_type):
    for instrument in instruments:
        try:
            kite.place_order (tradingsymbol=instrument,
                              variety=kite.VARIETY_REGULAR,
                              exchange=kite.EXCHANGE_NSE,
                              transaction_type=transaction_type,
                              quantity=LOTS,
                              order_type=kite.ORDER_TYPE_MARKET,
                              product=kite.PRODUCT_CNC,
                              # Need limit
                              price=None,
                              trigger_price=None,
                              tag=ORDER_TAG)
        except Exception:
            print (traceback.format_exc () + ' in Stock:' + str (instrument))


def get_min_sp(tick):
    if 'depth' in tick and 'sell' in tick['depth']:
        min_sp = math.inf
        for item in tick['depth']['sell']:
            if 0 < item['price'] < min_sp:
                min_sp = item['price']
        return min_sp
    return -1


def get_max_bp(tick):
    if 'depth' in tick and 'buy' in tick['depth']:
        max_bp = -math.inf
        for item in tick['depth']['buy']:
            if 0 < item['price'] > max_bp:
                max_bp = item['price']
        return max_bp
    return -1


def build_strikes_map(strike, type):
    return {'NFO:BANKNIFTY20APR' + str(strike) + type: {'tradingsymbol': 'BANKNIFTY20APR' + str(strike) + type, 'strike': strike, 'instrument_type': type}}


def get_atm_strike_symbols(l_spot_price, o_placed):
    atm_strike = int(math.ceil(l_spot_price / 100.0) * 100)

    s_to_trade = {}
    for i in range(-1100, 1100, 100):
        s_to_trade.update(build_strikes_map(atm_strike + i, 'CE'))
        s_to_trade.update (build_strikes_map(atm_strike + i, 'PE'))

    for key in o_placed.keys ():
        s_to_trade.update (build_strikes_map (key, 'CE'))
        s_to_trade.update (build_strikes_map (key, 'PE'))

    symbols = []
    for key, value in s_to_trade.items ():
        symbols.append (key)

    symbols.append (SPOT)
    return symbols, s_to_trade


def fetch_positions_set_orders_placed(kt):
    ors_placed = {}
    positions = kt.positions ()['net']
    for position in positions:
        nse_symbol = position['exchange'].upper () + ':' + position['tradingsymbol'].upper ()
        if position['quantity'] != 0 and nse_symbol in strikes_to_trade:
            strike = strikes_to_trade[nse_symbol]['strike']
            instrument_type = strikes_to_trade[nse_symbol]['instrument_type'].lower ()
            if strike in ors_placed:
                ors_placed[strike].update ({instrument_type + '_buy_value': position['buy_price']})
            else:
                ors_placed[strike] = {instrument_type + '_buy_value': position['buy_price']}

    return ors_placed


record_file = 'F:/Trading_Responses/BNStrikesTrader' + datetime.today ().strftime ("%Y_%m_%d") + '.txt'

# Initialise
kite = util.intialize_kite_api ()

# orders_placed = fetch_positions_set_orders_placed(kite)
orders_placed = {}

last_spot_price = kite.quote (SPOT)[SPOT]['last_price']

STRADDLE_LAST_TIME = d_time (14, 0, 0, 0)
indian_timezone = timezone ('Asia/Calcutta')
while datetime.now (indian_timezone).time () < util.MARKET_START_TIME:
    pass

while True:
    try:
        symbols, strikes_to_trade = get_atm_strike_symbols (last_spot_price, orders_placed)

        quotes = kite.quote (symbols)

        records = {}
        curr_time = datetime.now ()

        for nse_option_id, quote in quotes.items ():
            if nse_option_id == SPOT:
                last_spot_price = quote['last_price']
                continue

            min_sp = get_min_sp (quote)

            delay_in_fetch = [(quote['timestamp'] - curr_time).seconds, (curr_time - quote['timestamp']).seconds][
                curr_time > quote['timestamp']]

            if min_sp == -1 or min_sp == math.inf or delay_in_fetch > 10:
                continue

            max_bp = get_max_bp (quote)

            if strikes_to_trade[nse_option_id]['strike'] in records:
                records[strikes_to_trade[nse_option_id]['strike']].update ({strikes_to_trade[nse_option_id][
                                                                                'instrument_type']: [min_sp,
                                                                                                     quote['timestamp'],
                                                                                                     delay_in_fetch,
                                                                                                     max_bp,
                                                                                                     nse_option_id,
                                                                                                     quote[
                                                                                                         'last_price']]})
            else:
                records[strikes_to_trade[nse_option_id]['strike']] = {
                    strikes_to_trade[nse_option_id]['instrument_type']: [min_sp, quote['timestamp'], delay_in_fetch,
                                                                         max_bp, nse_option_id, quote['last_price']]}

        for strike, value in records.items ():

            if 'CE' in value and 'PE' in value:
                if len (orders_placed) < 4 and datetime.now (indian_timezone).time () <= STRADDLE_LAST_TIME and strike not in orders_placed:
                    for strike2, value2 in records.items ():
                        order_ce_key = str (strike) + 'CE' + str (strike2)
                        order_pe_key = str (strike) + 'PE' + str (strike2)

                        if 'CE' in value2 and 'PE' in value2:
                            if strike < strike2 and (value['PE'][3] - value2['PE'][0]) > 50:

                                orders_placed[order_pe_key] = {value['PE'][4]: value['PE'][3], value2['PE'][4]: value2['PE'][0]}
                                # place_buy_sell_order([value['CE'][4], value['PE'][4]], kite.TRANSACTION_TYPE_BUY)
                                lines_to_write = '\n####Bought lower:' + str (strike) + ' at PE:' + str (value['PE'][3]) + ' at upper PE:' + str (strike2)  + ' and PE:' + str (value2['PE'][0])
                                lines_to_write += '\n Quote lower PE:' + str (quotes[value['PE'][4]])
                                lines_to_write += '\n Quote PE:' + str (quotes[value2['PE'][4]]) + '\n'
                                with open (record_file, 'a') as file_object:
                                    file_object.write (lines_to_write)
                                print (lines_to_write)

                            if strike > strike2 and (value['CE'][3] - value2['CE'][0]) > 50:
                                orders_placed[order_ce_key] = {value['CE'][4]: value['CE'][3], value2['CE'][4]: value2['CE'][0]}
                                # place_buy_sell_order([value['CE'][4], value['PE'][4]], kite.TRANSACTION_TYPE_BUY)
                                lines_to_write = '\n####Bought lower:' + str (strike) + ' at CE:' + str (value['CE'][3]) + ' at upper CE:' + str (strike2) + ' and CE:' + str (value2['CE'][0])
                                lines_to_write += '\n Quote upper CE:' + str (quotes[value['CE'][4]])
                                lines_to_write += '\n Quote CE:' + str (quotes[value2['CE'][4]]) + '\n'
                                with open (record_file, 'a') as file_object:
                                    file_object.write (lines_to_write)
                                print (lines_to_write)

                        # if order_ce_key in orders_placed and :
                        #     pl = value['CE'][5] + value2['CE'][5] - orders_placed[strike]['ce_buy_value'] - \
                        #          orders_placed[strike]['pe_buy_value']
                        #     if 100 < pl or pl < -200:
                        #         del orders_placed[strike]
                        #         # place_buy_sell_order([value['CE'][4], value['PE'][4]], kite.TRANSACTION_TYPE_SELL)
                        #         lines_to_write = '\n@@@@Sold:' + str (strike) + ' at CE:' + str (
                        #             value['CE'][5]) + ' and PE:' + str (value['PE'][5]) + '. Sum:' + str (
                        #             value['CE'][5] + value['PE'][5]) + ' and PL:' + str (pl)
                        #         lines_to_write += '\n Quote CE:' + str (quotes[value['CE'][4]])
                        #         lines_to_write += '\n Quote CE:' + str (quotes[value['PE'][4]]) + '\n'
                        #         with open (record_file, 'a') as file_object:
                        #             file_object.write (lines_to_write)
                        #         print (lines_to_write)

        time.sleep (1)
    except Exception:
        print (traceback.format_exc ())
        # orders_placed = fetch_positions_set_orders_placed (kite)

