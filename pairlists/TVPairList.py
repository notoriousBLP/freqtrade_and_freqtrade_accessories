"""
TradingView Pair List provider

Provides TradingView pairs picked from white list as it configured in config
"""
from decimal import Decimal
from tradingview_ta import *
import logging
from copy import deepcopy
from typing import Any, Dict, List
from itertools import islice

from freqtrade.plugins.pairlist.IPairList import IPairList

import os
import time
import json
import pandas as pd
import re

logger = logging.getLogger(__name__)


def volatility_calculator(bollinger_band_upper, bollinger_band_lower):
    """
    A break away from traditional volatility calcuations. Based entirely
    on the proportionate price gap between bollinger upper and lower bands.
    """

    try:
        b_spread = Decimal(bollinger_band_upper) - Decimal(bollinger_band_lower)
    except TypeError:
        return 0
        
    return abs(b_spread / Decimal(bollinger_band_lower)) * 100

class TVPairList(IPairList):

    def __init__(self, exchange, pairlistmanager,
                 config: Dict[str, Any], pairlistconfig: Dict[str, Any],
                 pairlist_pos: int) -> None:
        super().__init__(exchange, pairlistmanager, config, pairlistconfig, pairlist_pos)

        self._granularity = self._pairlistconfig.get('granularity', '1d')
        self._adx_threshold = self._pairlistconfig.get('adx_threshold', 25)
        self._volatility_threshold = self._pairlistconfig.get('volatility_threshold', 5)
        self._volume_threshold = self._pairlistconfig.get('volume_threshold', 500000)
    
    @property
    def needstickers(self) -> bool:
        """
        Boolean property defining if tickers are necessary.
        If no Pairlist requires tickers, an empty Dict is passed
        as tickers argument to filter_pairlist
        """
        return False

    def short_desc(self) -> str:
        """
        Short whitelist method description - used for startup-messages
        -> Please overwrite in subclasses
        """
        return f"{self.name}"

    def gen_pairlist(self, tickers: Dict) -> List[str]:
        """
        Generate the pairlist
        :param tickers: Tickers (from exchange.get_tickers()). May be cached.
        :return: List of pairs
        """
        pair_list = []
        pair_list = self._whitelist_for_active_markets(self.verify_whitelist(self._config['exchange']['pair_whitelist'], logger.info))
        exchange_name = self._config['exchange']['name'].upper()
        ta_screener_list = [f"{re.sub('PRO', '', exchange_name, re.IGNORECASE)}:{re.sub('/', '', pair)}" for pair in pair_list]
        screener_analysis = []
        screener_analysis = get_multiple_analysis(screener='crypto', interval=self._granularity, symbols=ta_screener_list).values()

        coins = 0
        winningcoins = 0
        
        # Take what we need and do magic, ditch the rest.
        formatted_ta = []
        for ta in screener_analysis:
            try:
                recommend = Decimal(ta.indicators.get('Recommend.All'))
                volatility = Decimal(volatility_calculator(ta.indicators['BB.upper'], ta.indicators['BB.lower']))
                adx = abs(Decimal(ta.indicators['ADX']))
                adx_posi_di = Decimal(ta.indicators['ADX+DI'])
                adx_neg_di = Decimal(ta.indicators['ADX-DI'])
                volume = Decimal(ta.indicators['volume'])
                macd = Decimal(ta.indicators['MACD.macd'])
                macd_signal = Decimal(ta.indicators['MACD.signal'])
                bollinger_upper = Decimal(ta.indicators['BB.upper'])
                bollinger_lower = Decimal(ta.indicators['BB.lower'])
                rsi = Decimal(ta.indicators.get('RSI', 0))
                stoch_d = Decimal(ta.indicators.get('Stoch.D', 0))
                stoch_k = Decimal(ta.indicators.get('Stoch.K', 0))
                williams_r = Decimal(ta.indicators.get('W.R', 0))
                score = 0
                coins += 1
                if 0.5 >= recommend > 0.1:
                    score += 2.5
                    rating = 'BUY'
                elif recommend > 0.5:
                    score += 5
                    rating = 'STRONG_BUY'
                if (adx >= self._adx_threshold) and ((adx_posi_di > adx_neg_di) or (adx_posi_di > adx)):
                    score += 1 
                if volume >= self._volume_threshold:
                    score += 1
                if abs(macd) > abs(macd_signal):
                    score += 1
                if volatility >= self._volatility_threshold:
                    score += 1
                if 30 <= rsi > 10:
                    score += 1
                if 10 < stoch_d <= 30:
                    score += 1
                if stoch_k > stoch_d:
                    score += 1
                if williams_r <= -30:
                    score += 1
                if score >= 8:#
                    winningcoins += 1
                    chosen_coin = re.sub(self._config['stake_currency'],f"/{self._config['stake_currency']}", ta.symbol)
                    formatted_ta.append(chosen_coin)
            except Exception as e:
                #print(f"tvscreener error:{e}")
                pass
        
        #print(f"Coins: {coins}")
        # print(f"TradingView Picks: {winningcoins} {formatted_ta}")
        #return self._whitelist_for_active_markets(
        #    self.verify_whitelist(formatted_ta, logger.info))
        return formatted_ta[:self._pairlistconfig.get('number_assets', 10)]
    
    def filter_pairlist(self, pairlist: List[str], tickers: Dict) -> List[str]:
        """
        Filters and sorts pairlist and returns the whitelist again.
        Called on each bot iteration - please use internal caching if necessary
        :param pairlist: pairlist to filter or sort
        :param tickers: Tickers (from exchange.get_tickers()). May be cached.
        :return: new whitelist
        """
        pairlist_ = deepcopy(pairlist)
        for pair in self._config['exchange']['pair_whitelist']:
            if pair not in pairlist_:
                pairlist_.append(pair)
        return pairlist_
