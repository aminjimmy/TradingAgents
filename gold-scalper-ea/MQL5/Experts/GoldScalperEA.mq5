//+------------------------------------------------------------------+
//|                                                GoldScalperEA.mq5 |
//|  Multi-timeframe XAUUSD scalper for MT5 (built for OANDA MT5).   |
//|                                                                  |
//|  - Scalps M5, M15, M30 and H1 independently (one magic per TF)   |
//|  - Optional higher-timeframe trend filter (default H4 EMA50/200) |
//|  - 7-point indicator confluence score: EMA, RSI, MACD, ADX/DI,   |
//|    Bollinger, Stochastic, candle body; plus an entry trigger     |
//|    (EMA pullback bounce, fresh EMA cross, or Stochastic cross)   |
//|  - ATR-based SL/TP, break-even, ATR trailing stop, time exit     |
//|  - Hard limits: daily loss %, max trades/day, loss-streak        |
//|    cooldown, spread, session, Friday close, USD news filter      |
//|                                                                  |
//|  v1.10: default entry engine is RSI(2) mean reversion on H1,     |
//|  the only engine that showed an edge out-of-sample in the        |
//|  2020-2026 backtest. v1.00 confluence kept as a legacy option.   |
//|  v1.11: trade log CSV (Common\Files) for out-of-tester analysis. |
//+------------------------------------------------------------------+
#property copyright "aminjimmy"
#property version   "1.15"
#property description "XAUUSD EA: RSI(2) mean-reversion (default) or legacy indicator confluence, with hard risk limits. See backtest/RESULTS.md."

#include <Trade/Trade.mqh>

enum ENUM_ENTRY_MODE
  {
   ENTRY_MEAN_REVERSION = 0, // RSI(2) mean reversion (v1.10 default)
   ENTRY_CONFLUENCE     = 1  // Legacy v1.00 indicator confluence (lost money in backtest)
  };

//--- General
input group "=== General ==="
input long   InpMagic            = 770100;        // Base magic (M5=+0, M15=+1, M30=+2, H1=+3)
input string InpComment          = "GoldScalper"; // Order comment prefix
input ENUM_ENTRY_MODE InpEntryMode = ENTRY_MEAN_REVERSION; // Entry engine

//--- Mean reversion engine
input group "=== Mean-reversion engine (RSI-2) ==="
input int    InpMR_RsiPeriod     = 2;      // RSI period
input double InpMR_Level         = 10.0;   // Buy below this RSI / sell above 100-this
input int    InpMR_TrendEma      = 200;    // Only buy above / sell below this EMA
input int    InpMR_ExitEma       = 5;      // Exit when close crosses back over this EMA
input bool   InpUseDailyTrend    = false;  // Only buy when D1 close > D1 EMA, only sell when below (v1.13)
input int    InpDailyTrendEma    = 50;     // D1 EMA period for the daily trend filter
input bool   InpUseUsdFilter     = false;  // Only buy gold when the dollar fell over N days, only sell when it rose (v1.15)
input string InpUsdProxySymbol   = "EURUSD"; // Dollar proxy symbol (EURUSD, or a dollar index symbol if your broker has one)
input bool   InpUsdProxyInverted = true;   // true for EURUSD (EUR up = dollar down), false for a dollar index
input int    InpUsdLookbackDays  = 20;     // Days for the dollar trend

//--- Timeframes
input group "=== Timeframes to scalp ==="
input bool   InpUseM5            = false;  // Trade M5 signals (costs dominate - off)
input bool   InpUseM15           = false;  // Trade M15 signals
input bool   InpUseM30           = false;  // Trade M30 signals
input bool   InpUseH1            = true;   // Trade H1 signals

//--- Trend filter
input group "=== Higher-timeframe trend filter ==="
input bool            InpUseTrendFilter = false;     // Only trade with the HTF trend
input ENUM_TIMEFRAMES InpTrendTF        = PERIOD_H4; // Trend timeframe
input int             InpTrendEmaFast   = 50;        // Trend EMA fast
input int             InpTrendEmaSlow   = 200;       // Trend EMA slow

//--- Signal indicators
input group "=== Signal indicators ==="
input int    InpEmaFast          = 9;      // Signal EMA fast
input int    InpEmaSlow          = 21;     // Signal EMA slow
input int    InpRsiPeriod        = 14;     // RSI period
input double InpRsiBuyMax        = 70.0;   // Don't buy when RSI above
input double InpRsiSellMin       = 30.0;   // Don't sell when RSI below
input int    InpMacdFast         = 12;     // MACD fast
input int    InpMacdSlow         = 26;     // MACD slow
input int    InpMacdSignal       = 9;      // MACD signal
input int    InpAdxPeriod        = 14;     // ADX period
input double InpAdxMin           = 20.0;   // Minimum ADX (trend strength)
input bool   InpRequireAdx       = true;   // Block entries when ADX < minimum
input int    InpBBPeriod         = 20;     // Bollinger period
input double InpBBDev            = 2.0;    // Bollinger deviation
input int    InpStochK           = 5;      // Stochastic %K
input int    InpStochD           = 3;      // Stochastic %D
input int    InpStochSlow        = 3;      // Stochastic slowing
input double InpStochOB          = 80.0;   // Stochastic overbought
input double InpStochOS          = 20.0;   // Stochastic oversold
input int    InpAtrPeriod        = 14;     // ATR period
input int    InpMinScore         = 5;      // Min confluence score (out of 7)

//--- Risk
input group "=== Risk & money management ==="
input double InpRiskPercent      = 0.5;    // Risk per trade (% of equity)
input double InpFixedLots        = 0.0;    // Fixed lots (>0 overrides risk %)
input double InpFixedLotMaxRiskPct = 3.0;  // Skip a fixed-lot trade if its stop would risk more than this % (0=off)
input double InpLotGrowthStepUSD = 0.0;    // Add InpFixedLots for every $X of profit above the start balance (0=off)
input double InpGrowthStartBalance = 0.0;  // Start balance for lot growth (0 = balance when first attached, remembered)
input double InpMaxLots          = 5.0;    // Hard cap on lots per trade
input double InpSLAtrMult        = 2.0;    // Stop loss = ATR x this
input double InpRewardRisk       = 3.0;    // Take profit = SL x this (R:R)
input double InpMinSLPrice       = 1.00;   // Minimum SL distance in price ($)
input double InpFixedSLPrice     = 0.0;    // Fixed SL distance in price $ (0=use ATR). 10 = $10/oz = $10 on 0.01 lot of 100oz
input double InpFixedTPPrice     = 0.0;    // Fixed TP distance in price $ (0=use SL x R:R)
input int    InpMaxPosPerTF      = 1;      // Max open positions per timeframe
input int    InpMaxTotalPos      = 4;      // Max open positions total
input double InpMaxDailyLossPct  = 4.0;    // Stop + flatten at this daily loss % (0=off)
input double InpDailyTargetPct   = 0.0;    // Stop new trades at this daily gain % (0=off)
input int    InpMaxTradesPerDay  = 30;     // Max new trades per day (0=off)
input int    InpMaxConsecLosses  = 4;      // Loss streak that triggers cooldown (0=off)
input int    InpCooldownMin      = 60;     // Cooldown minutes after loss streak

//--- Trade management
input group "=== Trade management ==="
input double InpBreakEvenR       = 0.0;    // Move SL to break-even at this many R (0=off)
input double InpBELockPrice      = 0.10;   // Profit locked at break-even ($)
input double InpTrailStartR      = 0.0;    // Start ATR trailing at this many R (0=off)
input double InpTrailAtrMult     = 1.0;    // Trailing distance = ATR x this
input int    InpMaxBarsInTrade   = 24;     // Close after N bars of its timeframe (0=off)
input bool   InpCloseOnOpposite  = false;  // Close a TF's position on opposite signal

//--- Filters
input group "=== Market filters ==="
input double InpMaxSpreadPrice   = 0.50;   // Max spread in price ($)
input bool   InpUseSession       = true;   // Only open trades inside session hours
input int    InpSessionStartHour = 9;      // Session start (broker server hour)
input int    InpSessionEndHour   = 23;     // Session end (broker server hour)
input bool   InpFridayClose      = true;   // Flatten and stop on Friday evening
input int    InpFridayCloseHour  = 21;     // Friday close hour (server time)
input bool   InpUseNewsFilter    = true;   // Block around high-impact USD news (live only)
input int    InpNewsBeforeMin    = 30;     // Minutes before news
input int    InpNewsAfterMin     = 30;     // Minutes after news
input double InpMinAtrPrice      = 0.0;    // Skip if signal-TF ATR below ($, 0=off)
input double InpMaxAtrPrice      = 0.0;    // Skip if signal-TF ATR above ($, 0=off)
input int    InpSlippagePoints   = 50;     // Max slippage (points)
input bool   InpShowPanel        = true;   // Show status panel on chart

//--- Logging
input group "=== Logging ==="
input bool   InpLogTrades        = true;   // Write trades CSV to Terminal\Common\Files

//+------------------------------------------------------------------+
#define TF_COUNT 4

struct TFCtx
  {
   ENUM_TIMEFRAMES   tf;
   bool              on;
   long              magic;
   int               hEmaF;
   int               hEmaS;
   int               hRsi;
   int               hMacd;
   int               hAdx;
   int               hAtr;
   int               hBB;
   int               hSto;
   int               hMrRsi;
   int               hMrTrend;
   int               hMrExit;
   datetime          lastBar;
   string            lastInfo;
  };

CTrade   trade;
TFCtx    g_tf[TF_COUNT];
int      g_hTrendF = INVALID_HANDLE;
int      g_hTrendS = INVALID_HANDLE;
int      g_hDailyEma = INVALID_HANDLE;
double   g_growthStart = 0.0;

datetime g_day          = 0;
double   g_dayStartBal  = 0.0;
double   g_closedToday  = 0.0;
int      g_tradesToday  = 0;
int      g_consecLosses = 0;
datetime g_lastLossTime = 0;
bool     g_statsDirty   = true;
bool     g_haltedToday  = false;
string   g_haltReason   = "";
string   g_lastSignal   = "-";

// trade log state
datetime g_logFrom        = 0;
ulong    g_lastDealTicket = 0;
long     g_riskPos[];
double   g_riskVal[];
long     g_reasonPos[];
string   g_reasonTxt[];

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
string TFName(ENUM_TIMEFRAMES tf)
  {
   return StringSubstr(EnumToString(tf), 7);
  }

bool IsOurMagic(long m)
  {
   return (m >= InpMagic && m < InpMagic + TF_COUNT);
  }

datetime DayStart(datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t, d);
   d.hour = 0;
   d.min  = 0;
   d.sec  = 0;
   return StructToTime(d);
  }

double NormPrice(double p)
  {
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(ts > 0)
      p = MathRound(p / ts) * ts;
   return NormalizeDouble(p, _Digits);
  }

double NormLots(double lots)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0)
      step = 0.01;
   lots = MathFloor(lots / step + 1e-9) * step;
   if(InpMaxLots > 0)
      lots = MathMin(lots, InpMaxLots);
   lots = MathMin(lots, vmax);
   if(lots < vmin)
      return 0.0;
   int digits = (int)MathMax(0, MathCeil(-MathLog10(step)));
   return NormalizeDouble(lots, digits);
  }

// Copies 3 closed bars (shift 1..3) of an indicator buffer; a[0] = last closed bar.
bool Buf(int handle, int buffer, double &a[])
  {
   ArraySetAsSeries(a, true);
   return (CopyBuffer(handle, buffer, 1, 3, a) == 3);
  }

double AtrOf(int idx)
  {
   double a[];
   if(!Buf(g_tf[idx].hAtr, 0, a))
      return 0.0;
   return a[0];
  }

double StopsMinDist()
  {
   long stops  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freeze = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   return (double)(stops > freeze ? stops : freeze) * _Point;
  }

//+------------------------------------------------------------------+
//| Trade log (columns match the xau-backtest-analyst bt_analyze.py) |
//+------------------------------------------------------------------+
string LogFile()
  {
   return (MQLInfoInteger(MQL_TESTER) ? "TEST_" : "") + "GoldScalper_" + _Symbol + "_" +
          IntegerToString(InpMagic) + "_trades.csv";
  }

void LogLine(string line)
  {
   int h = FileOpen(LogFile(), FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   if(FileSize(h) == 0)
      FileWriteString(h, "time,event,position_id,profit_net,r_multiple,setup,regime,session,confidence,exit_reason\r\n");
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, line + "\r\n");
   FileClose(h);
  }

string SessionName(datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t, d);
   if(d.hour < 9)
      return "Asia";
   if(d.hour < 15)
      return "London";
   if(d.hour < 20)
      return "NewYork";
   return "Late";
  }

void RememberReason(long posId, string why)
  {
   int n = ArraySize(g_reasonPos);
   ArrayResize(g_reasonPos, n + 1);
   ArrayResize(g_reasonTxt, n + 1);
   g_reasonPos[n] = posId;
   g_reasonTxt[n] = why;
  }

string TakeReason(long posId)
  {
   for(int i = ArraySize(g_reasonPos) - 1; i >= 0; i--)
      if(g_reasonPos[i] == posId)
         return g_reasonTxt[i];
   return "expert";
  }

double RiskOf(long posId)
  {
   for(int i = ArraySize(g_riskPos) - 1; i >= 0; i--)
      if(g_riskPos[i] == posId)
         return g_riskVal[i];
   return 0.0;
  }

void ProcessNewDeals()
  {
   if(!InpLogTrades)
      return;
   if(!HistorySelect(g_logFrom, TimeCurrent() + 60))
      return;
   ulong tickets[];
   int cnt = 0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
     {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0 || tk <= g_lastDealTicket)
         continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol || !IsOurMagic(HistoryDealGetInteger(tk, DEAL_MAGIC)))
         continue;
      ArrayResize(tickets, cnt + 1);
      tickets[cnt++] = tk;
     }
   for(int k = 0; k < cnt; k++)
     {
      ulong tk = tickets[k];
      if(tk > g_lastDealTicket)
         g_lastDealTicket = tk;
      if(!HistoryDealSelect(tk))
         continue;
      long     entry = HistoryDealGetInteger(tk, DEAL_ENTRY);
      long     posId = HistoryDealGetInteger(tk, DEAL_POSITION_ID);
      long     mg    = HistoryDealGetInteger(tk, DEAL_MAGIC);
      long     type  = HistoryDealGetInteger(tk, DEAL_TYPE);
      datetime t     = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
      double   price = HistoryDealGetDouble(tk, DEAL_PRICE);
      double   vol   = HistoryDealGetDouble(tk, DEAL_VOLUME);
      double   net   = HistoryDealGetDouble(tk, DEAL_PROFIT) + HistoryDealGetDouble(tk, DEAL_SWAP) +
                       HistoryDealGetDouble(tk, DEAL_COMMISSION);
      long     reason = HistoryDealGetInteger(tk, DEAL_REASON);
      ulong    order = (ulong)HistoryDealGetInteger(tk, DEAL_ORDER);
      int      idx   = (int)(mg - InpMagic);
      string   tf    = (idx >= 0 && idx < TF_COUNT) ? TFName(g_tf[idx].tf) : "?";
      string   regime = (InpEntryMode == ENTRY_MEAN_REVERSION) ? "mean_rev" : "confluence";
      string   ts    = TimeToString(t, TIME_DATE | TIME_SECONDS);
      if(entry == DEAL_ENTRY_IN)
        {
         double sl = 0.0;
         if(HistoryOrderSelect(order))
            sl = HistoryOrderGetDouble(order, ORDER_SL);
         double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
         if(tv <= 0)
            tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
         double ts_ = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
         double risk = (sl > 0 && ts_ > 0) ? MathAbs(price - sl) / ts_ * tv * vol : 0.0;
         int m = ArraySize(g_riskPos);
         ArrayResize(g_riskPos, m + 1);
         ArrayResize(g_riskVal, m + 1);
         g_riskPos[m] = posId;
         g_riskVal[m] = risk;
         string setup = tf + (type == DEAL_TYPE_BUY ? "_BUY" : "_SELL");
         LogLine(StringFormat("%s,OPEN,%I64d,,,%s,%s,%s,0,", ts, posId, setup, regime, SessionName(t)));
        }
      else
         if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY || entry == DEAL_ENTRY_INOUT)
           {
            double risk = RiskOf(posId);
            string why = (reason == DEAL_REASON_SL) ? "sl" : (reason == DEAL_REASON_TP) ? "tp" : TakeReason(posId);
            string setup = tf + (type == DEAL_TYPE_SELL ? "_BUY" : "_SELL");
            LogLine(StringFormat("%s,CLOSE,%I64d,%.2f,%.3f,%s,%s,%s,0,%s", ts, posId, net,
                                 risk > 0 ? net / risk : 0.0, setup, regime, SessionName(t), why));
           }
     }
  }

//+------------------------------------------------------------------+
//| Position helpers                                                 |
//+------------------------------------------------------------------+
int CountPositions(long magic) // magic < 0 => all of ours
  {
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      if(magic < 0 ? IsOurMagic(m) : (m == magic))
         n++;
     }
   return n;
  }

double FloatingPnL()
  {
   double sum = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if(!IsOurMagic(PositionGetInteger(POSITION_MAGIC)))
         continue;
      sum += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
     }
   return sum;
  }

void CloseWhere(long magic, int dirToClose, string why) // magic<0 all ours; dir 0 = both
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      if(!(magic < 0 ? IsOurMagic(m) : (m == magic)))
         continue;
      long type = PositionGetInteger(POSITION_TYPE);
      int dir = (type == POSITION_TYPE_BUY) ? 1 : -1;
      if(dirToClose != 0 && dir != dirToClose)
         continue;
      RememberReason(PositionGetInteger(POSITION_IDENTIFIER), why);
      if(trade.PositionClose(tk))
         PrintFormat("Closed #%I64u (%s)", tk, why);
      else
         PrintFormat("Close #%I64u failed: %d %s", tk, trade.ResultRetcode(), trade.ResultRetcodeDescription());
      g_statsDirty = true;
     }
  }

//+------------------------------------------------------------------+
//| Daily statistics (closed P/L, trade count, loss streak)          |
//+------------------------------------------------------------------+
void UpdateDailyStats()
  {
   datetime now = TimeCurrent();
   datetime ds  = DayStart(now);
   bool newDay  = (ds != g_day);
   if(!newDay && !g_statsDirty)
      return;
   g_statsDirty   = false;
   g_closedToday  = 0.0;
   g_tradesToday  = 0;
   g_consecLosses = 0;
   g_lastLossTime = 0;

   if(HistorySelect(ds, now + 60))
     {
      int n = HistoryDealsTotal();
      for(int i = 0; i < n; i++)
        {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0)
            continue;
         if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol)
            continue;
         if(!IsOurMagic(HistoryDealGetInteger(tk, DEAL_MAGIC)))
            continue;
         long   entry = HistoryDealGetInteger(tk, DEAL_ENTRY);
         double comm  = HistoryDealGetDouble(tk, DEAL_COMMISSION);
         if(entry == DEAL_ENTRY_IN)
           {
            g_tradesToday++;
            g_closedToday += comm;
            continue;
           }
         if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY || entry == DEAL_ENTRY_INOUT)
           {
            double pnl = HistoryDealGetDouble(tk, DEAL_PROFIT) + HistoryDealGetDouble(tk, DEAL_SWAP) + comm;
            g_closedToday += pnl;
            if(pnl < 0)
              {
               g_consecLosses++;
               g_lastLossTime = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
              }
            else
               if(pnl > 0)
                  g_consecLosses = 0;
           }
        }
     }

   if(newDay)
     {
      g_day         = ds;
      g_dayStartBal = AccountInfoDouble(ACCOUNT_BALANCE) - g_closedToday;
      g_haltedToday = false;
      g_haltReason  = "";
     }
  }

//+------------------------------------------------------------------+
//| Risk gate                                                        |
//+------------------------------------------------------------------+
bool RiskAllowsTrading(string &reason)
  {
   double dayPnL = g_closedToday + FloatingPnL();
   if(g_dayStartBal > 0 && InpMaxDailyLossPct > 0 &&
      dayPnL <= -g_dayStartBal * InpMaxDailyLossPct / 100.0)
     {
      if(CountPositions(-1) > 0)
         CloseWhere(-1, 0, "daily loss limit");
      g_haltedToday = true;
      g_haltReason  = "Daily loss limit hit";
     }
   if(!g_haltedToday && g_dayStartBal > 0 && InpDailyTargetPct > 0 &&
      dayPnL >= g_dayStartBal * InpDailyTargetPct / 100.0)
     {
      g_haltedToday = true;
      g_haltReason  = "Daily profit target reached";
     }
   if(g_haltedToday)
     {
      reason = g_haltReason;
      return false;
     }
   if(InpMaxTradesPerDay > 0 && g_tradesToday >= InpMaxTradesPerDay)
     {
      reason = "Max trades per day reached";
      return false;
     }
   if(InpMaxConsecLosses > 0 && g_consecLosses >= InpMaxConsecLosses &&
      TimeCurrent() - g_lastLossTime < InpCooldownMin * 60)
     {
      reason = StringFormat("Cooldown after %d losses", g_consecLosses);
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Market gate                                                      |
//+------------------------------------------------------------------+
bool NewsBlocked()
  {
   if(!InpUseNewsFilter || MQLInfoInteger(MQL_TESTER))
      return false;
   static datetime lastCheck = 0;
   static bool     blocked   = false;
   datetime now = TimeTradeServer();
   if(now - lastCheck < 60)
      return blocked;
   lastCheck = now;
   blocked   = false;
   MqlCalendarValue vals[];
   int n = CalendarValueHistory(vals, now - InpNewsAfterMin * 60, now + InpNewsBeforeMin * 60, NULL, "USD");
   for(int i = 0; i < n; i++)
     {
      MqlCalendarEvent ev;
      if(CalendarEventById(vals[i].event_id, ev) && ev.importance == CALENDAR_IMPORTANCE_HIGH)
        {
         blocked = true;
         break;
        }
     }
   return blocked;
  }

bool InSession(int hour)
  {
   if(!InpUseSession)
      return true;
   if(InpSessionStartHour == InpSessionEndHour)
      return true;
   if(InpSessionStartHour < InpSessionEndHour)
      return (hour >= InpSessionStartHour && hour < InpSessionEndHour);
   return (hour >= InpSessionStartHour || hour < InpSessionEndHour); // wraps midnight
  }

bool MarketAllowsTrading(string &reason)
  {
   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t))
     {
      reason = "No tick";
      return false;
     }
   if(t.ask - t.bid > InpMaxSpreadPrice)
     {
      reason = StringFormat("Spread %.2f > %.2f", t.ask - t.bid, InpMaxSpreadPrice);
      return false;
     }
   MqlDateTime d;
   TimeToStruct(TimeCurrent(), d);
   if(InpFridayClose && d.day_of_week == 5 && d.hour >= InpFridayCloseHour)
     {
      reason = "Friday close";
      return false;
     }
   if(!InSession(d.hour))
     {
      reason = "Outside session";
      return false;
     }
   if(NewsBlocked())
     {
      reason = "High-impact USD news";
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Higher-timeframe trend: 1 up, -1 down, 0 none                    |
//+------------------------------------------------------------------+
int TrendDir()
  {
   double f[], s[], c[];
   if(!Buf(g_hTrendF, 0, f) || !Buf(g_hTrendS, 0, s))
      return 0;
   ArraySetAsSeries(c, true);
   if(CopyClose(_Symbol, InpTrendTF, 1, 1, c) != 1)
      return 0;
   if(c[0] > s[0] && f[0] > s[0])
      return 1;
   if(c[0] < s[0] && f[0] < s[0])
      return -1;
   return 0;
  }

//+------------------------------------------------------------------+
//| Signal for one timeframe: 1 buy, -1 sell, 0 none                 |
//+------------------------------------------------------------------+
int Signal(int idx, string &info)
  {
   ENUM_TIMEFRAMES tf = g_tf[idx].tf;
   double emaF[], emaS[], rsi[], mM[], mS[], adx[], pdi[], mdi[], atr[];
   double bbM[], bbU[], bbL[], stK[], stD[], o[], h[], l[], c[];

   if(!Buf(g_tf[idx].hEmaF, 0, emaF) || !Buf(g_tf[idx].hEmaS, 0, emaS) ||
      !Buf(g_tf[idx].hRsi, 0, rsi)   || !Buf(g_tf[idx].hMacd, 0, mM)  || !Buf(g_tf[idx].hMacd, 1, mS) ||
      !Buf(g_tf[idx].hAdx, 0, adx)   || !Buf(g_tf[idx].hAdx, 1, pdi)  || !Buf(g_tf[idx].hAdx, 2, mdi) ||
      !Buf(g_tf[idx].hAtr, 0, atr)   || !Buf(g_tf[idx].hBB, 0, bbM)   || !Buf(g_tf[idx].hBB, 1, bbU) ||
      !Buf(g_tf[idx].hBB, 2, bbL)    || !Buf(g_tf[idx].hSto, 0, stK)  || !Buf(g_tf[idx].hSto, 1, stD))
     {
      info = "indicator data not ready";
      return 0;
     }
   ArraySetAsSeries(o, true);
   ArraySetAsSeries(h, true);
   ArraySetAsSeries(l, true);
   ArraySetAsSeries(c, true);
   if(CopyOpen(_Symbol, tf, 1, 3, o) != 3 || CopyHigh(_Symbol, tf, 1, 3, h) != 3 ||
      CopyLow(_Symbol, tf, 1, 3, l) != 3  || CopyClose(_Symbol, tf, 1, 3, c) != 3)
     {
      info = "price data not ready";
      return 0;
     }

   double a = atr[0];
   if(InpMinAtrPrice > 0 && a < InpMinAtrPrice)
     {
      info = StringFormat("ATR %.2f too low", a);
      return 0;
     }
   if(InpMaxAtrPrice > 0 && a > InpMaxAtrPrice)
     {
      info = StringFormat("ATR %.2f too high", a);
      return 0;
     }

   int sl = 0, ss = 0;
   // 1) EMA alignment
   if(emaF[0] > emaS[0])
      sl++;
   if(emaF[0] < emaS[0])
      ss++;
   // 2) RSI momentum, not stretched
   if(rsi[0] > 50 && rsi[0] < InpRsiBuyMax && rsi[0] > rsi[1])
      sl++;
   if(rsi[0] < 50 && rsi[0] > InpRsiSellMin && rsi[0] < rsi[1])
      ss++;
   // 3) MACD histogram on the right side and expanding
   double h0 = mM[0] - mS[0], h1 = mM[1] - mS[1];
   if(h0 > 0 && h0 > h1)
      sl++;
   if(h0 < 0 && h0 < h1)
      ss++;
   // 4) ADX strength + DI direction
   bool adxOk = (adx[0] >= InpAdxMin);
   if(adxOk && pdi[0] > mdi[0])
      sl++;
   if(adxOk && mdi[0] > pdi[0])
      ss++;
   // 5) Bollinger: correct half of the band, not outside it
   if(c[0] > bbM[0] && c[0] < bbU[0])
      sl++;
   if(c[0] < bbM[0] && c[0] > bbL[0])
      ss++;
   // 6) Stochastic direction, not exhausted
   if(stK[0] > stD[0] && stK[0] < InpStochOB)
      sl++;
   if(stK[0] < stD[0] && stK[0] > InpStochOS)
      ss++;
   // 7) Decisive candle body
   double rng = h[0] - l[0];
   double body = c[0] - o[0];
   if(rng > 0 && body > 0 && body >= 0.35 * rng)
      sl++;
   if(rng > 0 && body < 0 && -body >= 0.35 * rng)
      ss++;

   // Entry triggers (need at least one)
   bool trigL = (emaF[0] > emaS[0] && l[0] <= emaF[0] + 0.25 * a && c[0] > emaF[0])   // pullback bounce
                || (emaF[1] <= emaS[1] && emaF[0] > emaS[0])                         // fresh EMA cross
                || (stK[1] <= stD[1] && stK[0] > stD[0] && stK[1] < 50);             // stoch cross up
   bool trigS = (emaF[0] < emaS[0] && h[0] >= emaF[0] - 0.25 * a && c[0] < emaF[0])
                || (emaF[1] >= emaS[1] && emaF[0] < emaS[0])
                || (stK[1] >= stD[1] && stK[0] < stD[0] && stK[1] > 50);

   info = StringFormat("%s L%d/S%d ADX%.0f RSI%.0f ATR%.2f", TFName(tf), sl, ss, adx[0], rsi[0], a);

   if(InpRequireAdx && !adxOk)
      return 0;

   int dir = 0;
   if(sl >= InpMinScore && sl > ss && trigL)
      dir = 1;
   else
      if(ss >= InpMinScore && ss > sl && trigS)
         dir = -1;

   if(dir != 0 && InpUseTrendFilter)
     {
      int tr = TrendDir();
      if(tr != dir)
        {
         info += " (against HTF trend)";
         return 0;
        }
     }
   return dir;
  }

//+------------------------------------------------------------------+
//| RSI(2) mean reversion: 1 buy, -1 sell, 0 none; also exit flags   |
//+------------------------------------------------------------------+
int SignalMR(int idx, string &info, bool &exitLong, bool &exitShort)
  {
   exitLong = false;
   exitShort = false;
   double r[], tr[], x[], atr[], c[];
   if(!Buf(g_tf[idx].hMrRsi, 0, r) || !Buf(g_tf[idx].hMrTrend, 0, tr) ||
      !Buf(g_tf[idx].hMrExit, 0, x) || !Buf(g_tf[idx].hAtr, 0, atr))
     {
      info = "indicator data not ready";
      return 0;
     }
   ArraySetAsSeries(c, true);
   if(CopyClose(_Symbol, g_tf[idx].tf, 1, 3, c) != 3)
     {
      info = "price data not ready";
      return 0;
     }
   exitLong  = (c[0] > x[0]);
   exitShort = (c[0] < x[0]);
   info = StringFormat("%s RSI%d=%.1f %s EMA%d ATR%.2f", TFName(g_tf[idx].tf), InpMR_RsiPeriod, r[0],
                       c[0] > tr[0] ? "above" : "below", InpMR_TrendEma, atr[0]);
   if(InpMinAtrPrice > 0 && atr[0] < InpMinAtrPrice)
      return 0;
   if(InpMaxAtrPrice > 0 && atr[0] > InpMaxAtrPrice)
      return 0;
   int dir = 0;
   if(c[0] > tr[0] && r[0] < InpMR_Level)
      dir = 1;
   else
      if(c[0] < tr[0] && r[0] > 100.0 - InpMR_Level)
         dir = -1;
   if(dir != 0 && InpUseTrendFilter && TrendDir() != dir)
     {
      info += " (against HTF trend)";
      return 0;
     }
   if(dir != 0 && InpUseDailyTrend)
     {
      double de[], dc[];
      ArraySetAsSeries(dc, true);
      if(!Buf(g_hDailyEma, 0, de) || CopyClose(_Symbol, PERIOD_D1, 1, 1, dc) != 1)
        {
         info = "indicator data not ready";
         return 0;
        }
      int dailyDir = (dc[0] > de[0]) ? 1 : -1;
      if(dailyDir != dir)
        {
         info += " (against daily trend)";
         return 0;
        }
     }
   if(dir != 0 && InpUseUsdFilter)
     {
      double pc[];
      ArraySetAsSeries(pc, true);
      int need = InpUsdLookbackDays + 1;
      if(CopyClose(InpUsdProxySymbol, PERIOD_D1, 1, need, pc) != need || pc[InpUsdLookbackDays] <= 0)
        {
         info = "indicator data not ready";   // retried on the next tick
         return 0;
        }
      double chg = pc[0] / pc[InpUsdLookbackDays] - 1.0;
      double usdChg = InpUsdProxyInverted ? -chg : chg;
      if((dir > 0 && usdChg >= 0) || (dir < 0 && usdChg <= 0))
        {
         info += StringFormat(" (dollar %+.2f%% over %dd: not supportive)", usdChg * 100, InpUsdLookbackDays);
         return 0;
        }
     }
   return dir;
  }

//+------------------------------------------------------------------+
//| Lot sizing from risk %                                           |
//+------------------------------------------------------------------+
double CalcLots(double slDist)
  {
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tickVal <= 0)
      tickVal = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickVal <= 0 || tickSize <= 0 || slDist <= 0)
      return 0.0;
   double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
   double lossPerLot = slDist / tickSize * tickVal;
   if(InpFixedLots > 0)
     {
      double units = 1.0;
      if(InpLotGrowthStepUSD > 0 && g_growthStart > 0)
         units += MathFloor(MathMax(0.0, AccountInfoDouble(ACCOUNT_BALANCE) - g_growthStart) / InpLotGrowthStepUSD);
      double lots = NormLots(InpFixedLots * units);
      double riskPct = equity > 0 ? lots * lossPerLot / equity * 100.0 : 100.0;
      if(InpFixedLotMaxRiskPct > 0 && riskPct > InpFixedLotMaxRiskPct)
        {
         PrintFormat("Fixed %.2f lots would risk %.1f%% of equity (stop %.2f) > %.1f%% cap - trade skipped",
                     lots, riskPct, slDist, InpFixedLotMaxRiskPct);
         return 0.0;
        }
      return lots;
     }
   return NormLots(equity * InpRiskPercent / 100.0 / lossPerLot);
  }

//+------------------------------------------------------------------+
//| Open a trade                                                     |
//+------------------------------------------------------------------+
void OpenTrade(int idx, int dir)
  {
   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t))
      return;
   double a = AtrOf(idx);
   if(a <= 0)
      return;
   double spread = t.ask - t.bid;
   double minD   = StopsMinDist() + spread;
   double slDist = (InpFixedSLPrice > 0) ? MathMax(InpFixedSLPrice, minD)
                                         : MathMax(MathMax(a * InpSLAtrMult, InpMinSLPrice), minD);
   double tpDist = (InpFixedTPPrice > 0) ? MathMax(InpFixedTPPrice, minD)
                                         : MathMax(slDist * InpRewardRisk, minD);

   double price = (dir > 0) ? t.ask : t.bid;
   double sl    = NormPrice(dir > 0 ? price - slDist : price + slDist);
   double tp    = NormPrice(dir > 0 ? price + tpDist : price - tpDist);

   double lots = CalcLots(slDist);
   if(lots <= 0)
     {
      Print("Lot size below broker minimum - increase risk or balance");
      return;
     }
   // Shrink to fit free margin
   ENUM_ORDER_TYPE ot = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double margin = 0.0;
   double freeM  = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(OrderCalcMargin(ot, _Symbol, lots, price, margin) && margin > freeM * 0.9 && margin > 0)
     {
      lots = NormLots(lots * freeM * 0.9 / margin);
      if(lots <= 0)
        {
         Print("Not enough free margin");
         return;
        }
     }

   trade.SetExpertMagicNumber(g_tf[idx].magic);
   string cmt = InpComment + " " + TFName(g_tf[idx].tf);
   bool ok = (dir > 0) ? trade.Buy(lots, _Symbol, price, sl, tp, cmt)
                       : trade.Sell(lots, _Symbol, price, sl, tp, cmt);
   PrintFormat("%s %s %.2f lots @%.2f SL %.2f TP %.2f -> %s (%d)",
               TFName(g_tf[idx].tf), dir > 0 ? "BUY" : "SELL", lots, price, sl, tp,
               ok ? "OK" : "FAILED", trade.ResultRetcode());
   g_statsDirty = true;
  }

//+------------------------------------------------------------------+
//| Manage open positions: time exit, break-even, trailing           |
//+------------------------------------------------------------------+
void ManagePositions()
  {
   MqlDateTime d;
   TimeToStruct(TimeCurrent(), d);
   if(InpFridayClose && d.day_of_week == 5 && d.hour >= InpFridayCloseHour && CountPositions(-1) > 0)
     {
      CloseWhere(-1, 0, "Friday close");
      return;
     }

   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t))
      return;
   double minD = StopsMinDist();

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      long mg = PositionGetInteger(POSITION_MAGIC);
      if(!IsOurMagic(mg))
         continue;
      int idx = (int)(mg - InpMagic);

      long     type = PositionGetInteger(POSITION_TYPE);
      double   open = PositionGetDouble(POSITION_PRICE_OPEN);
      double   sl   = PositionGetDouble(POSITION_SL);
      double   tp   = PositionGetDouble(POSITION_TP);
      datetime ot   = (datetime)PositionGetInteger(POSITION_TIME);

      // Time-based exit
      if(InpMaxBarsInTrade > 0 &&
         TimeCurrent() - ot >= (long)InpMaxBarsInTrade * PeriodSeconds(g_tf[idx].tf))
        {
         RememberReason(PositionGetInteger(POSITION_IDENTIFIER), "time");
         if(trade.PositionClose(tk))
            PrintFormat("Closed #%I64u (time exit)", tk);
         g_statsDirty = true;
         continue;
        }

      // Initial risk R recovered from the fixed TP
      if(tp <= 0 || InpRewardRisk <= 0)
         continue;
      double R = (InpFixedSLPrice > 0) ? InpFixedSLPrice
                 : (InpFixedTPPrice > 0 ? 0.0 : MathAbs(tp - open) / InpRewardRisk);
      if(R <= 0)
         continue;
      double a = AtrOf(idx);
      double step = MathMax(a * 0.05, _Point * 5);

      if(type == POSITION_TYPE_BUY)
        {
         double prof  = t.bid - open;
         double newSL = sl;
         if(InpBreakEvenR > 0 && prof >= InpBreakEvenR * R)
            newSL = MathMax(newSL, open + InpBELockPrice);
         if(InpTrailStartR > 0 && a > 0 && prof >= InpTrailStartR * R)
            newSL = MathMax(newSL, t.bid - a * InpTrailAtrMult);
         newSL = NormPrice(newSL);
         if(newSL > sl + step && t.bid - newSL > minD)
            trade.PositionModify(tk, newSL, tp);
        }
      else
        {
         double prof  = open - t.ask;
         double cur   = (sl > 0) ? sl : DBL_MAX;
         double newSL = cur;
         if(InpBreakEvenR > 0 && prof >= InpBreakEvenR * R)
            newSL = MathMin(newSL, open - InpBELockPrice);
         if(InpTrailStartR > 0 && a > 0 && prof >= InpTrailStartR * R)
            newSL = MathMin(newSL, t.ask + a * InpTrailAtrMult);
         if(newSL < cur)
           {
            newSL = NormPrice(newSL);
            if(newSL < cur - step && newSL - t.ask > minD)
               trade.PositionModify(tk, newSL, tp);
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Status panel                                                     |
//+------------------------------------------------------------------+
void DrawPanel(string blockReason)
  {
   double dayPnL = g_closedToday + FloatingPnL();
   string s = "GoldScalperEA v1.15 [" + (InpEntryMode == ENTRY_MEAN_REVERSION ? "RSI2 mean-rev" : "confluence") + "]  |  " + _Symbol + "\n";
   s += StringFormat("Day P/L: %.2f (%.2f%%)  trades today: %d  loss streak: %d\n",
                     dayPnL, g_dayStartBal > 0 ? dayPnL / g_dayStartBal * 100.0 : 0.0,
                     g_tradesToday, g_consecLosses);
   s += StringFormat("Open positions: %d / %d   HTF trend: %s\n", CountPositions(-1), InpMaxTotalPos,
                     !InpUseTrendFilter ? "off" : (TrendDir() > 0 ? "UP" : (TrendDir() < 0 ? "DOWN" : "flat")));
   s += "Status: " + (blockReason == "" ? "ACTIVE" : "PAUSED - " + blockReason) + "\n";
   for(int i = 0; i < TF_COUNT; i++)
      if(g_tf[i].on)
         s += StringFormat("  %-4s pos:%d  %s\n", TFName(g_tf[i].tf), CountPositions(g_tf[i].magic), g_tf[i].lastInfo);
   s += "Last signal: " + g_lastSignal;
   Comment(s);
  }

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpEmaFast >= InpEmaSlow || InpRewardRisk <= 0 || InpSLAtrMult <= 0 ||
      InpMinScore < 1 || InpMinScore > 7 || InpRiskPercent < 0 ||
      InpMR_RsiPeriod < 1 || InpMR_Level <= 0 || InpMR_Level >= 50)
     {
      Print("Invalid inputs: check EMA periods, R:R, SL multiplier, min score (1-7), risk %");
      return INIT_PARAMETERS_INCORRECT;
     }

   ENUM_TIMEFRAMES tfs[TF_COUNT] = {PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1};
   for(int i = 0; i < TF_COUNT; i++)
     {
      ENUM_TIMEFRAMES tf = tfs[i];
      g_tf[i].tf       = tf;
      g_tf[i].magic    = InpMagic + i;
      g_tf[i].lastInfo = "";
      g_tf[i].hEmaF    = iMA(_Symbol, tf, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
      g_tf[i].hEmaS    = iMA(_Symbol, tf, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
      g_tf[i].hRsi     = iRSI(_Symbol, tf, InpRsiPeriod, PRICE_CLOSE);
      g_tf[i].hMacd    = iMACD(_Symbol, tf, InpMacdFast, InpMacdSlow, InpMacdSignal, PRICE_CLOSE);
      g_tf[i].hAdx     = iADX(_Symbol, tf, InpAdxPeriod);
      g_tf[i].hAtr     = iATR(_Symbol, tf, InpAtrPeriod);
      g_tf[i].hBB      = iBands(_Symbol, tf, InpBBPeriod, 0, InpBBDev, PRICE_CLOSE);
      g_tf[i].hSto     = iStochastic(_Symbol, tf, InpStochK, InpStochD, InpStochSlow, MODE_SMA, STO_LOWHIGH);
      g_tf[i].hMrRsi   = iRSI(_Symbol, tf, InpMR_RsiPeriod, PRICE_CLOSE);
      g_tf[i].hMrTrend = iMA(_Symbol, tf, InpMR_TrendEma, 0, MODE_EMA, PRICE_CLOSE);
      g_tf[i].hMrExit  = iMA(_Symbol, tf, InpMR_ExitEma, 0, MODE_EMA, PRICE_CLOSE);
      g_tf[i].lastBar  = iTime(_Symbol, tf, 0); // don't fire on a stale bar at attach time
      if(g_tf[i].hEmaF == INVALID_HANDLE || g_tf[i].hEmaS == INVALID_HANDLE || g_tf[i].hRsi == INVALID_HANDLE ||
         g_tf[i].hMacd == INVALID_HANDLE || g_tf[i].hAdx == INVALID_HANDLE || g_tf[i].hAtr == INVALID_HANDLE ||
         g_tf[i].hBB == INVALID_HANDLE || g_tf[i].hSto == INVALID_HANDLE ||
         g_tf[i].hMrRsi == INVALID_HANDLE || g_tf[i].hMrTrend == INVALID_HANDLE || g_tf[i].hMrExit == INVALID_HANDLE)
        {
         Print("Failed to create indicator handles for ", TFName(tf));
         return INIT_FAILED;
        }
     }
   g_tf[0].on = InpUseM5;
   g_tf[1].on = InpUseM15;
   g_tf[2].on = InpUseM30;
   g_tf[3].on = InpUseH1;

   g_hTrendF = iMA(_Symbol, InpTrendTF, InpTrendEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   g_hTrendS = iMA(_Symbol, InpTrendTF, InpTrendEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   g_hDailyEma = iMA(_Symbol, PERIOD_D1, InpDailyTrendEma, 0, MODE_EMA, PRICE_CLOSE);
   if(InpUseUsdFilter && !SymbolSelect(InpUsdProxySymbol, true))
     {
      Print("Dollar proxy symbol not found: ", InpUsdProxySymbol, " - check the exact name in Market Watch");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(g_hTrendF == INVALID_HANDLE || g_hTrendS == INVALID_HANDLE || g_hDailyEma == INVALID_HANDLE)
     {
      Print("Failed to create trend handles");
      return INIT_FAILED;
     }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetAsyncMode(false);

   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
      Print("Warning: EA is tuned for gold (XAUUSD) but attached to ", _Symbol);

   // lot-growth reference balance (kept across restarts in a terminal global variable)
   string gv = "GoldScalper_" + IntegerToString(InpMagic) + "_growthStart";
   if(InpGrowthStartBalance > 0)
      g_growthStart = InpGrowthStartBalance;
   else
      if(!MQLInfoInteger(MQL_TESTER) && GlobalVariableCheck(gv))
         g_growthStart = GlobalVariableGet(gv);
      else
        {
         g_growthStart = AccountInfoDouble(ACCOUNT_BALANCE);
         if(!MQLInfoInteger(MQL_TESTER))
            GlobalVariableSet(gv, g_growthStart);
        }
   g_logFrom = TimeCurrent();
   g_lastDealTicket = 0;
   g_day = 0;
   g_statsDirty = true;
   UpdateDailyStats();
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   ProcessNewDeals();
   for(int i = 0; i < TF_COUNT; i++)
     {
      IndicatorRelease(g_tf[i].hEmaF);
      IndicatorRelease(g_tf[i].hEmaS);
      IndicatorRelease(g_tf[i].hRsi);
      IndicatorRelease(g_tf[i].hMacd);
      IndicatorRelease(g_tf[i].hAdx);
      IndicatorRelease(g_tf[i].hAtr);
      IndicatorRelease(g_tf[i].hBB);
      IndicatorRelease(g_tf[i].hSto);
      IndicatorRelease(g_tf[i].hMrRsi);
      IndicatorRelease(g_tf[i].hMrTrend);
      IndicatorRelease(g_tf[i].hMrExit);
     }
   IndicatorRelease(g_hTrendF);
   IndicatorRelease(g_hTrendS);
   IndicatorRelease(g_hDailyEma);
   Comment("");
  }

//+------------------------------------------------------------------+
void OnTrade()
  {
   g_statsDirty = true;
   ProcessNewDeals();
  }

//+------------------------------------------------------------------+
//| Main loop                                                        |
//+------------------------------------------------------------------+
void OnTick()
  {
   UpdateDailyStats();
   ManagePositions();

   string reason = "";
   bool canTrade = RiskAllowsTrading(reason) && MarketAllowsTrading(reason);

   for(int i = 0; i < TF_COUNT; i++)
     {
      if(!g_tf[i].on)
         continue;
      datetime bt = iTime(_Symbol, g_tf[i].tf, 0);
      if(bt == 0 || bt == g_tf[i].lastBar)
         continue;

      string info = "";
      bool exitL = false, exitS = false;
      int dir = (InpEntryMode == ENTRY_MEAN_REVERSION) ? SignalMR(i, info, exitL, exitS) : Signal(i, info);
      if(info == "indicator data not ready" || info == "price data not ready")
         continue; // retry on next tick
      if(exitL)
         CloseWhere(g_tf[i].magic, 1, "exit EMA cross");
      if(exitS)
         CloseWhere(g_tf[i].magic, -1, "exit EMA cross");
      g_tf[i].lastBar  = bt;
      g_tf[i].lastInfo = info;
      if(dir == 0)
         continue;

      g_lastSignal = StringFormat("%s %s @ %s", TFName(g_tf[i].tf), dir > 0 ? "BUY" : "SELL",
                                  TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES));
      if(InpCloseOnOpposite)
         CloseWhere(g_tf[i].magic, -dir, "opposite signal");

      if(!canTrade)
         continue;
      if(CountPositions(g_tf[i].magic) >= InpMaxPosPerTF)
         continue;
      if(CountPositions(-1) >= InpMaxTotalPos)
         continue;
      OpenTrade(i, dir);
     }

   if(InpShowPanel)
      DrawPanel(canTrade ? "" : reason);
  }
//+------------------------------------------------------------------+
