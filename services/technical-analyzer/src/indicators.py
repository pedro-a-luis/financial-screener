"""
Technical Indicators Calculator
Calculates all 20+ technical indicators from price data
Uses pandas-ta library for comprehensive indicator support
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, List, Optional
from datetime import date, datetime
import structlog

logger = structlog.get_logger()


class TechnicalIndicatorCalculator:
    """Calculate technical indicators from OHLCV price data."""

    def __init__(self):
        """Initialize calculator."""
        self.indicators = {}

    def calculate_all_indicators(
        self,
        prices: List[Dict],
        ticker: str = None
    ) -> Dict:
        """
        Calculate all technical indicators from price data.

        Args:
            prices: List of price dicts with keys: date, open, high, low, close, volume
            ticker: Stock ticker (for logging)

        Returns:
            Dictionary with all calculated indicators (latest values)
        """
        if not prices or len(prices) < 200:
            logger.warning(
                "insufficient_data_for_indicators",
                ticker=ticker,
                data_points=len(prices) if prices else 0
            )
            return {}

        # Convert to DataFrame
        df = pd.DataFrame(prices)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df.set_index('date', inplace=True)

        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        results = {}

        try:
            # 1. MOVING AVERAGES
            results['sma_50'] = self._calculate_sma(df, 50)
            results['sma_200'] = self._calculate_sma(df, 200)
            results['ema_12'] = self._calculate_ema(df, 12)
            results['ema_26'] = self._calculate_ema(df, 26)
            results['wma_20'] = self._calculate_wma(df, 20)

            # 2. MOMENTUM INDICATORS
            results['rsi_14'] = self._calculate_rsi(df, 14)
            results['stoch_k'], results['stoch_d'] = self._calculate_stochastic(df)
            results['stoch_rsi'] = self._calculate_stochastic_rsi(df)
            results['cci_20'] = self._calculate_cci(df, 20)

            # 3. TREND INDICATORS
            macd_data = self._calculate_macd(df)
            results['macd'] = macd_data['macd']
            results['macd_signal'] = macd_data['signal']
            results['macd_histogram'] = macd_data['histogram']

            dmi_data = self._calculate_dmi(df)
            results['dmi_plus'] = dmi_data['dmi_plus']
            results['dmi_minus'] = dmi_data['dmi_minus']
            results['adx'] = dmi_data['adx']

            # 4. VOLATILITY INDICATORS
            results['atr_14'] = self._calculate_atr(df, 14)
            results['volatility'] = self._calculate_volatility(df)
            results['std_dev'] = self._calculate_stddev(df, 20)

            bb_data = self._calculate_bollinger_bands(df)
            results['bb_upper'] = bb_data['upper']
            results['bb_middle'] = bb_data['middle']
            results['bb_lower'] = bb_data['lower']
            results['bb_bandwidth'] = bb_data['bandwidth']

            # 5. OTHER INDICATORS
            results['sar'] = self._calculate_parabolic_sar(df)
            results['beta'] = self._calculate_beta(df)  # vs SPY
            results['slope'] = self._calculate_slope(df, 20)

            # 6. VOLUME INDICATORS
            results['avg_volume_30'] = self._calculate_avg_volume(df, 30)
            results['avg_volume_90'] = self._calculate_avg_volume(df, 90)

            # 7. PRICE LEVELS
            results['week_52_high'] = float(df['high'].rolling(252).max().iloc[-1])
            results['week_52_low'] = float(df['low'].rolling(252).min().iloc[-1])
            results['current_price'] = float(df['close'].iloc[-1])

            logger.info(
                "indicators_calculated",
                ticker=ticker,
                indicators_count=len(results)
            )

            return results

        except Exception as e:
            logger.error(
                "indicator_calculation_failed",
                ticker=ticker,
                error=str(e)
            )
            return {}

    def _calculate_sma(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Simple Moving Average."""
        sma = ta.sma(df['close'], length=period)
        return float(sma.iloc[-1]) if not pd.isna(sma.iloc[-1]) else None

    def _calculate_ema(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Exponential Moving Average."""
        ema = ta.ema(df['close'], length=period)
        return float(ema.iloc[-1]) if not pd.isna(ema.iloc[-1]) else None

    def _calculate_wma(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Weighted Moving Average."""
        wma = ta.wma(df['close'], length=period)
        return float(wma.iloc[-1]) if not pd.isna(wma.iloc[-1]) else None

    def _calculate_rsi(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Relative Strength Index."""
        rsi = ta.rsi(df['close'], length=period)
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None

    def _calculate_stochastic(self, df: pd.DataFrame) -> tuple:
        """Stochastic Oscillator (K and D lines)."""
        stoch = ta.stoch(df['high'], df['low'], df['close'])
        k = float(stoch['STOCHk_14_3_3'].iloc[-1]) if not pd.isna(stoch['STOCHk_14_3_3'].iloc[-1]) else None
        d = float(stoch['STOCHd_14_3_3'].iloc[-1]) if not pd.isna(stoch['STOCHd_14_3_3'].iloc[-1]) else None
        return k, d

    def _calculate_stochastic_rsi(self, df: pd.DataFrame) -> Optional[float]:
        """Stochastic RSI."""
        stoch_rsi = ta.stochrsi(df['close'])
        return float(stoch_rsi['STOCHRSIk_14_14_3_3'].iloc[-1]) if not pd.isna(stoch_rsi['STOCHRSIk_14_14_3_3'].iloc[-1]) else None

    def _calculate_macd(self, df: pd.DataFrame) -> Dict:
        """MACD (Moving Average Convergence Divergence)."""
        macd = ta.macd(df['close'])
        return {
            'macd': float(macd['MACD_12_26_9'].iloc[-1]) if not pd.isna(macd['MACD_12_26_9'].iloc[-1]) else None,
            'signal': float(macd['MACDs_12_26_9'].iloc[-1]) if not pd.isna(macd['MACDs_12_26_9'].iloc[-1]) else None,
            'histogram': float(macd['MACDh_12_26_9'].iloc[-1]) if not pd.isna(macd['MACDh_12_26_9'].iloc[-1]) else None,
        }

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Average True Range."""
        atr = ta.atr(df['high'], df['low'], df['close'], length=period)
        return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None

    def _calculate_cci(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Commodity Channel Index."""
        cci = ta.cci(df['high'], df['low'], df['close'], length=period)
        return float(cci.iloc[-1]) if not pd.isna(cci.iloc[-1]) else None

    def _calculate_bollinger_bands(self, df: pd.DataFrame) -> Dict:
        """Bollinger Bands."""
        bb = ta.bbands(df['close'], length=20, std=2)
        return {
            'upper': float(bb['BBU_20_2.0'].iloc[-1]) if not pd.isna(bb['BBU_20_2.0'].iloc[-1]) else None,
            'middle': float(bb['BBM_20_2.0'].iloc[-1]) if not pd.isna(bb['BBM_20_2.0'].iloc[-1]) else None,
            'lower': float(bb['BBL_20_2.0'].iloc[-1]) if not pd.isna(bb['BBL_20_2.0'].iloc[-1]) else None,
            'bandwidth': float(bb['BBB_20_2.0'].iloc[-1]) if not pd.isna(bb['BBB_20_2.0'].iloc[-1]) else None,
        }

    def _calculate_dmi(self, df: pd.DataFrame) -> Dict:
        """Directional Movement Index and ADX."""
        adx_data = ta.adx(df['high'], df['low'], df['close'])
        return {
            'dmi_plus': float(adx_data['DMp_14'].iloc[-1]) if not pd.isna(adx_data['DMp_14'].iloc[-1]) else None,
            'dmi_minus': float(adx_data['DMn_14'].iloc[-1]) if not pd.isna(adx_data['DMn_14'].iloc[-1]) else None,
            'adx': float(adx_data['ADX_14'].iloc[-1]) if not pd.isna(adx_data['ADX_14'].iloc[-1]) else None,
        }

    def _calculate_parabolic_sar(self, df: pd.DataFrame) -> Optional[float]:
        """Parabolic SAR."""
        sar = ta.psar(df['high'], df['low'], df['close'])
        return float(sar['PSARl_0.02_0.2'].iloc[-1]) if not pd.isna(sar['PSARl_0.02_0.2'].iloc[-1]) else float(sar['PSARs_0.02_0.2'].iloc[-1]) if not pd.isna(sar['PSARs_0.02_0.2'].iloc[-1]) else None

    def _calculate_volatility(self, df: pd.DataFrame, period: int = 30) -> Optional[float]:
        """Historical Volatility (annualized standard deviation of returns)."""
        returns = df['close'].pct_change()
        volatility = returns.rolling(period).std() * np.sqrt(252) * 100  # Annualized %
        return float(volatility.iloc[-1]) if not pd.isna(volatility.iloc[-1]) else None

    def _calculate_stddev(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Standard Deviation."""
        std = df['close'].rolling(period).std()
        return float(std.iloc[-1]) if not pd.isna(std.iloc[-1]) else None

    def _calculate_beta(self, df: pd.DataFrame, market_df: Optional[pd.DataFrame] = None) -> Optional[float]:
        """
        Beta (vs market).
        Note: Requires market index data (SPY).
        For now, return None - will implement when we add market data collection.
        """
        # TODO: Implement beta calculation vs SPY
        return None

    def _calculate_slope(self, df: pd.DataFrame, period: int) -> Optional[float]:
        """Linear regression slope."""
        slope = ta.slope(df['close'], length=period)
        return float(slope.iloc[-1]) if not pd.isna(slope.iloc[-1]) else None

    def _calculate_avg_volume(self, df: pd.DataFrame, period: int) -> Optional[int]:
        """Average Volume."""
        avg_vol = df['volume'].rolling(period).mean()
        return int(avg_vol.iloc[-1]) if not pd.isna(avg_vol.iloc[-1]) else None
