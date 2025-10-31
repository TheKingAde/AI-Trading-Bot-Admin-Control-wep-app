//+------------------------------------------------------------------+
//|                                                  DailyCB_scalper |
//|                     Copyright 2024, Meffun Adegoke (Bot Dev), TSA |
//+------------------------------------------------------------------+
#property copyright "Copyright 2024, Meffun Adegoke (Bot Dev), TSA"
#property link      "x.com/kingade_1"
#property version   "1.11"

#include <Trade\Trade.mqh>

input string user = "Ade";
input double LotSize = 0.01;
input int ATR_Period = 14;
input double ATR_Multiplier = 0.5;
input double SL_ATR_Multiplier = 1.0;
input double TP_ATR_Multiplier = 2.0;
input bool use_breakeven = true;
input int magic_number = 307037;

CTrade m_trade;
CPositionInfo m_position;
int atrHandle, ema20Handle, ema50Handle, rsiHandle;

// Buffers
double atrValue[];
double atrBuffer[], ema20Buffer[], ema50Buffer[], rsiBuffer[];
bool allow_buy_trade = true;
bool allow_sell_trade = true;
string m_comment = "DailyCB Scalper";

// Breakout vars
double upperBreakout = 0.0;
double lowerBreakout = 0.0;
datetime lastBreakoutTime = 0;
double bal;
double ini_bal;

const string TG_API_URL = "https://api.telegram.org";
string botTkn = "7969763015:AAEliO2m1l9Yn7dDY8j_PKvG3_4yHlXbuZY";
string chatID = "6126141848";
string current_time;
string message;

// Structure to store pending trade data
struct PendingTrade
  {
   string            unique_id;     // Custom unique identifier (PRIMARY KEY)
   string            action;
   double            entry;
   double            sl;
   double            tp;
   datetime          trade_time;
   
   // === MARKET STATE FEATURES (Pre-Entry) ===
   
   // Volatility & Price Action
   double            atr_14d;              // Daily ATR(14) - absolute volatility
   double            atr_pct;              // ATR as % of price - normalized volatility
   double            price_to_atr_ratio;   // Current price / ATR - volatility-adjusted price level
   double            daily_range_pct;      // Yesterday's range as % of close
   double            intraday_range_pct;   // Current day's range so far as % of open
   
   // Multi-Timeframe Momentum
   double            ret_1d;               // 1-day return
   double            ret_5d;               // 5-day return
   double            ret_10d;              // 10-day return
   double            ret_20d;              // 20-day return
   double            price_vs_ma20;        // Distance from 20-day MA (%)
   double            price_vs_ma50;        // Distance from 50-day MA (%)
   double            ma20_vs_ma50;         // MA crossover strength (%)
   
   // Mean Reversion Indicators
   double            rsi_14;               // RSI(14) on H1
   double            rsi_distance_50;      // How far RSI is from neutral 50
   double            price_vs_high_30d;    // Distance from 30-day high (%)
   double            price_vs_low_30d;     // Distance from 30-day low (%)
   double            price_position_30d;   // Where price sits in 30-day range (0-1)
   
   // Breakout Quality Metrics
   double            breakout_strength;    // How far beyond breakout level (in ATRs)
   double            volume_surge;         // Current volume vs 20-period average (if available)
   double            time_at_level;        // Hours spent near breakout level before break
   double            prev_day_close_pos;   // Where prev day closed in its range (0-1)
   
   // Session & Time Features
   int               hour_of_day;          // 0-23 (captures session effects)
   int               day_of_week;          // 1-5 (Monday to Friday)
   int               week_of_month;        // 1-4/5
   bool              is_london_session;    // 8-16 GMT
   bool              is_ny_session;        // 13-21 GMT
   bool              is_asian_session;     // 0-8 GMT
   
   // Recent Price Behavior (Last 3 H1 Candles)
   double            recent_volatility_surge; // Recent 3H volatility vs average
   double            recent_momentum;         // Sum of last 3 body sizes (directional)
   double            recent_rejection_strength; // Wick-to-body ratio (last 3 candles avg)
   int               bullish_candles_3h;      // Count of bullish candles in last 3H
   
   // Risk-Adjusted Metrics
   double            risk_reward_ratio;    // (TP-Entry)/(Entry-SL)
   double            sl_distance_atr;      // SL distance in ATRs
   double            tp_distance_atr;      // TP distance in ATRs
   double            edge_quality;         // Combined score: RR * breakout_strength * volatility_regime
  };

// Array to store pending trades
PendingTrade pendingTrades[];

// Global counter for unique IDs (simple incrementing number)
static int trade_counter = 1;

//+------------------------------------------------------------------+
//| Initialization                                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   m_trade.SetExpertMagicNumber(magic_number);
   m_trade.SetAsyncMode(true);
   m_trade.SetDeviationInPoints(30);

// --- Indicator Handles ---
   atrHandle   = iATR(_Symbol, PERIOD_D1, ATR_Period);
   ema20Handle = iMA(_Symbol, PERIOD_D1, 20, 0, MODE_EMA, PRICE_CLOSE);  // Changed to D1 for daily trend
   ema50Handle = iMA(_Symbol, PERIOD_D1, 50, 0, MODE_EMA, PRICE_CLOSE);  // Changed to D1 for daily trend
   rsiHandle   = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);

   if(atrHandle == INVALID_HANDLE || ema20Handle == INVALID_HANDLE ||
      ema50Handle == INVALID_HANDLE || rsiHandle == INVALID_HANDLE)
     {
      Print("Error creating indicator handles. Code: ", _LastError);
      return(INIT_FAILED);
     }

   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(atrHandle   != INVALID_HANDLE)
      IndicatorRelease(atrHandle);
   if(ema20Handle != INVALID_HANDLE)
      IndicatorRelease(ema20Handle);
   if(ema50Handle != INVALID_HANDLE)
      IndicatorRelease(ema50Handle);
   if(rsiHandle   != INVALID_HANDLE)
      IndicatorRelease(rsiHandle);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   double curr_ask_price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double curr_bid_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   datetime currentDayTime = iTime(_Symbol, PERIOD_D1, 0);
   if(lastBreakoutTime != currentDayTime)
     {
      lastBreakoutTime = currentDayTime;

      double prevHigh = iHigh(_Symbol, PERIOD_D1, 1);
      double prevLow  = iLow(_Symbol, PERIOD_D1, 1);

      if(CopyBuffer(atrHandle, 0, 0, 1, atrValue) <= 0)
        {
         Print("Error retrieving ATR value. Code: ", _LastError);
         return;
        }

      upperBreakout = prevHigh + (atrValue[0] * ATR_Multiplier);
      lowerBreakout = prevLow  - (atrValue[0] * ATR_Multiplier);

      double levels[] = {lowerBreakout, upperBreakout};

      double curr_daily_high = iHigh(_Symbol, PERIOD_D1, 0);
      double curr_daily_low  = iLow(_Symbol, PERIOD_D1, 0);

      if(curr_daily_high > upperBreakout || curr_daily_low < lowerBreakout)
        {
         allow_buy_trade = false;
         allow_sell_trade = false;
         Print("Price already broken out before EA initialization, skipping trade for the day");
        }
      else
        {
         allow_buy_trade = true;
         allow_sell_trade = true;
        }
     }

// ✅ BUY condition
   if(curr_ask_price > upperBreakout && allow_buy_trade)
     {
      double stopLoss   = NormalizeDouble(upperBreakout - (atrValue[0] * SL_ATR_Multiplier), _Digits);
      double takeProfit = NormalizeDouble(upperBreakout + (atrValue[0] * TP_ATR_Multiplier), _Digits);

      // Generate custom unique ID
      string unique_trade_id = GenerateUniqueID("BUY");

      // Set comment with unique ID for matching (very short format)
      string trade_comment = m_comment + "_" + unique_trade_id;

      Print("DEBUG: BUY trade comment: '", trade_comment, "' (length: ", StringLen(trade_comment), "), ID: ", unique_trade_id);

      if(m_trade.Buy(LotSize, _Symbol, 0.0, stopLoss, takeProfit, trade_comment))
        {
         StorePendingTrade("BUY", unique_trade_id, curr_bid_price, stopLoss, takeProfit, atrValue[0], use_breakeven);
         allow_buy_trade = false;
         allow_sell_trade = false;
        }
     }

// ✅ SELL condition
   if(curr_bid_price < lowerBreakout && allow_sell_trade)
     {
      double stopLoss   = NormalizeDouble(lowerBreakout + (atrValue[0] * SL_ATR_Multiplier), _Digits);
      double takeProfit = NormalizeDouble(lowerBreakout - (atrValue[0] * TP_ATR_Multiplier), _Digits);

      // Generate custom unique ID
      string unique_trade_id = GenerateUniqueID("SELL");

      // Set comment with unique ID for matching (very short format)
      string trade_comment = m_comment + "_" + unique_trade_id;

      Print("DEBUG: SELL trade comment: '", trade_comment, "' (length: ", StringLen(trade_comment), "), ID: ", unique_trade_id);

      if(m_trade.Sell(LotSize, _Symbol, 0.0, stopLoss, takeProfit, trade_comment))
        {
         StorePendingTrade("SELL", unique_trade_id, curr_ask_price, stopLoss, takeProfit, atrValue[0], use_breakeven);
         allow_buy_trade = false;
         allow_sell_trade = false;
        }
     }

   if(use_breakeven)
      break_even();
  }
//+------------------------------------------------------------------+
//| Generate Unique Trade ID                                         |
//+------------------------------------------------------------------+
string GenerateUniqueID(string action)
  {
// Use simple incrementing number as unique ID to avoid MT5 truncation issues
// Format: ACTION_NUMBER (e.g., BUY_1, SELL_2, BUY_3, etc.)
   string unique_id = StringFormat("%s_%d", action, trade_counter);

   trade_counter++; // Increment for next trade
   return unique_id;
  }

//+------------------------------------------------------------------+
//| Build CSV for 7 pre-breakout H1 candles                         |
//| Outputs for each of the 7 closed candles BEFORE breakout:       |
//|  Open, High, Low, Close, BodyPts, UpperWickPts, LowerWickPts     |
//| Candle 1 is the most recent closed H1 before breakout,          |
//| Candle 7 is the oldest in that window.                           |
//+------------------------------------------------------------------+
string BuildPreBreakoutCandlesCSV(datetime breakout_time)
  {
   string s = "";

   // Find the H1 bar that contains the breakout time
   int brk_bar = iBarShift(_Symbol, PERIOD_H1, breakout_time, false);
   if(brk_bar < 0)
     {
      // Fallback: use current bar as reference
      brk_bar = 0;
     }

   // Ensure sufficient bars exist
   int total_bars = Bars(_Symbol, PERIOD_H1);

   for(int k = 1; k <= 7; k++)
     {
      int shift = brk_bar + k; // closed candles before the breakout bar
      if(shift >= total_bars)
        {
         // Not enough history; pad with zeros
         s += DoubleToString(0.0, _Digits) + ";"; // Open
         s += DoubleToString(0.0, _Digits) + ";"; // High
         s += DoubleToString(0.0, _Digits) + ";"; // Low
         s += DoubleToString(0.0, _Digits) + ";"; // Close
         s += IntegerToString(0) + ";";           // BodyPts
         s += IntegerToString(0) + ";";           // UpperWickPts
         s += IntegerToString(0) + ";";           // LowerWickPts
         continue;
        }

      double o = iOpen(_Symbol, PERIOD_H1, shift);
      double h = iHigh(_Symbol, PERIOD_H1, shift);
      double l = iLow(_Symbol, PERIOD_H1, shift);
      double c = iClose(_Symbol, PERIOD_H1, shift);

      int body_pts = (int)MathRound(MathAbs(c - o) / _Point);
      double upper_wick = h - MathMax(o, c);
      double lower_wick = MathMin(o, c) - l;
      if(upper_wick < 0) upper_wick = 0; // guard against tiny negatives
      if(lower_wick < 0) lower_wick = 0;
      int upper_pts = (int)MathRound(upper_wick / _Point);
      int lower_pts = (int)MathRound(lower_wick / _Point);

      s += DoubleToString(o, _Digits) + ";";
      s += DoubleToString(h, _Digits) + ";";
      s += DoubleToString(l, _Digits) + ";";
      s += DoubleToString(c, _Digits) + ";";
      s += IntegerToString(body_pts) + ";";
      s += IntegerToString(upper_pts) + ";";
      s += IntegerToString(lower_pts) + ";";
     }

   return s;
  }

//+------------------------------------------------------------------+
//| Calculate Advanced Market State Features                        |
//+------------------------------------------------------------------+
void CalculateMarketFeatures(PendingTrade &trade)
  {
   double current_price = (trade.action == "BUY") ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   
   // === Copy indicator buffers ===
   double atr_buf[], ma20_buf[], ma50_buf[], rsi_buf[];
   ArraySetAsSeries(atr_buf, true);
   ArraySetAsSeries(ma20_buf, true);
   ArraySetAsSeries(ma50_buf, true);
   ArraySetAsSeries(rsi_buf, true);
   
   if(CopyBuffer(atrHandle, 0, 0, 14, atr_buf) <= 0) return;
   if(CopyBuffer(ema20Handle, 0, 0, 50, ma20_buf) <= 0) return;
   if(CopyBuffer(ema50Handle, 0, 0, 50, ma50_buf) <= 0) return;
   if(CopyBuffer(rsiHandle, 0, 0, 14, rsi_buf) <= 0) return;
   
   // === VOLATILITY FEATURES ===
   trade.atr_14d = atr_buf[0];
   trade.atr_pct = (current_price > 0) ? (trade.atr_14d / current_price) : 0.0;
   trade.price_to_atr_ratio = (trade.atr_14d > 0) ? (current_price / trade.atr_14d) : 0.0;
   
   double prev_high = iHigh(_Symbol, PERIOD_D1, 1);
   double prev_low = iLow(_Symbol, PERIOD_D1, 1);
   double prev_close = iClose(_Symbol, PERIOD_D1, 1);
   double prev_range = prev_high - prev_low;
   trade.daily_range_pct = (prev_close > 0) ? (prev_range / prev_close) : 0.0;
   
   double curr_high = iHigh(_Symbol, PERIOD_D1, 0);
   double curr_low = iLow(_Symbol, PERIOD_D1, 0);
   double curr_open = iOpen(_Symbol, PERIOD_D1, 0);
   double curr_range = curr_high - curr_low;
   trade.intraday_range_pct = (curr_open > 0) ? (curr_range / curr_open) : 0.0;
   
   // === MOMENTUM FEATURES (Multi-Timeframe) ===
   double close_1d_ago = iClose(_Symbol, PERIOD_D1, 1);
   double close_5d_ago = iClose(_Symbol, PERIOD_D1, 5);
   double close_10d_ago = iClose(_Symbol, PERIOD_D1, 10);
   double close_20d_ago = iClose(_Symbol, PERIOD_D1, 20);
   
   trade.ret_1d = (close_1d_ago > 0) ? (current_price / close_1d_ago - 1.0) : 0.0;
   trade.ret_5d = (close_5d_ago > 0) ? (current_price / close_5d_ago - 1.0) : 0.0;
   trade.ret_10d = (close_10d_ago > 0) ? (current_price / close_10d_ago - 1.0) : 0.0;
   trade.ret_20d = (close_20d_ago > 0) ? (current_price / close_20d_ago - 1.0) : 0.0;
   
   trade.price_vs_ma20 = (ma20_buf[0] > 0) ? ((current_price - ma20_buf[0]) / ma20_buf[0]) : 0.0;
   trade.price_vs_ma50 = (ma50_buf[0] > 0) ? ((current_price - ma50_buf[0]) / ma50_buf[0]) : 0.0;
   trade.ma20_vs_ma50 = (ma50_buf[0] > 0) ? ((ma20_buf[0] - ma50_buf[0]) / ma50_buf[0]) : 0.0;
   
   // === MEAN REVERSION FEATURES ===
   trade.rsi_14 = rsi_buf[0];
   trade.rsi_distance_50 = trade.rsi_14 - 50.0;
   
   double high_30d = iHigh(_Symbol, PERIOD_D1, iHighest(_Symbol, PERIOD_D1, MODE_HIGH, 30, 1));
   double low_30d = iLow(_Symbol, PERIOD_D1, iLowest(_Symbol, PERIOD_D1, MODE_LOW, 30, 1));
   
   trade.price_vs_high_30d = (current_price > 0) ? ((high_30d - current_price) / current_price) : 0.0;
   trade.price_vs_low_30d = (current_price > 0) ? ((current_price - low_30d) / current_price) : 0.0;
   
   double range_30d = high_30d - low_30d;
   trade.price_position_30d = (range_30d > 0) ? ((current_price - low_30d) / range_30d) : 0.5;
   
   // === BREAKOUT QUALITY ===
   double breakout_level = (trade.action == "BUY") ? upperBreakout : lowerBreakout;
   double breakout_distance = MathAbs(current_price - breakout_level);
   trade.breakout_strength = (trade.atr_14d > 0) ? (breakout_distance / trade.atr_14d) : 0.0;
   
   // Volume surge (if tick volume available)
   double recent_volume = 0, avg_volume = 0;
   for(int i = 0; i < 3; i++)
      recent_volume += (double)iVolume(_Symbol, PERIOD_H1, i);
   for(int i = 3; i < 23; i++)
      avg_volume += (double)iVolume(_Symbol, PERIOD_H1, i);
   
   avg_volume = avg_volume / 20.0;
   trade.volume_surge = (avg_volume > 0) ? (recent_volume / 3.0) / avg_volume : 1.0;
   
   // Time at level (hours spent within 0.5*ATR of breakout level in last 24H)
   trade.time_at_level = 0;
   double threshold = trade.atr_14d * 0.5;
   for(int i = 1; i <= 24; i++)
     {
      double h1_close = iClose(_Symbol, PERIOD_H1, i);
      if(MathAbs(h1_close - breakout_level) <= threshold)
         trade.time_at_level++;
     }
   
   // Previous day close position in range
   double prev_day_range = prev_high - prev_low;
   trade.prev_day_close_pos = (prev_day_range > 0) ? ((prev_close - prev_low) / prev_day_range) : 0.5;
   
   // === SESSION & TIME FEATURES ===
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   
   trade.hour_of_day = dt.hour;
   trade.day_of_week = dt.day_of_week;
   trade.week_of_month = (int)MathCeil(dt.day / 7.0);
   
   // Session identification (GMT-based)
   trade.is_asian_session = (dt.hour >= 0 && dt.hour < 8);
   trade.is_london_session = (dt.hour >= 8 && dt.hour < 16);
   trade.is_ny_session = (dt.hour >= 13 && dt.hour < 21);
   
   // === RECENT PRICE BEHAVIOR (Last 3 H1 Candles) ===
   double recent_atr = 0, avg_atr = 0;
   for(int i = 1; i <= 3; i++)
     {
      double h_high = iHigh(_Symbol, PERIOD_H1, i);
      double h_low = iLow(_Symbol, PERIOD_H1, i);
      recent_atr += (h_high - h_low);
     }
   for(int i = 4; i <= 23; i++)
     {
      double h_high = iHigh(_Symbol, PERIOD_H1, i);
      double h_low = iLow(_Symbol, PERIOD_H1, i);
      avg_atr += (h_high - h_low);
     }
   recent_atr = recent_atr / 3.0;
   avg_atr = avg_atr / 20.0;
   trade.recent_volatility_surge = (avg_atr > 0) ? (recent_atr / avg_atr) : 1.0;
   
   // Recent momentum (directional body sum)
   trade.recent_momentum = 0;
   trade.bullish_candles_3h = 0;
   double total_wick = 0, total_body = 0;
   
   for(int i = 1; i <= 3; i++)
     {
      double h_open = iOpen(_Symbol, PERIOD_H1, i);
      double h_close = iClose(_Symbol, PERIOD_H1, i);
      double h_high = iHigh(_Symbol, PERIOD_H1, i);
      double h_low = iLow(_Symbol, PERIOD_H1, i);
      
      double body = h_close - h_open; // Directional
      trade.recent_momentum += body;
      
      if(body > 0)
         trade.bullish_candles_3h++;
      
      double abs_body = MathAbs(body);
      double upper_wick = h_high - MathMax(h_open, h_close);
      double lower_wick = MathMin(h_open, h_close) - h_low;
      
      total_body += abs_body;
      total_wick += (upper_wick + lower_wick);
     }
   
   trade.recent_rejection_strength = (total_body > 0) ? (total_wick / total_body) : 0.0;
   
   // === RISK-ADJUSTED METRICS ===
   double risk = MathAbs(trade.entry - trade.sl);
   double reward = MathAbs(trade.tp - trade.entry);
   
   trade.risk_reward_ratio = (risk > 0) ? (reward / risk) : 0.0;
   trade.sl_distance_atr = (trade.atr_14d > 0) ? (risk / trade.atr_14d) : 0.0;
   trade.tp_distance_atr = (trade.atr_14d > 0) ? (reward / trade.atr_14d) : 0.0;
   
   // Edge quality composite score
   double volatility_regime = (trade.atr_pct > 0.01) ? 1.2 : 0.8; // High vol bonus
   trade.edge_quality = trade.risk_reward_ratio * trade.breakout_strength * volatility_regime;
  }

//+------------------------------------------------------------------+
//| Store Pending Trade Data                                         |
//+------------------------------------------------------------------+
void StorePendingTrade(string action, string unique_id, double entry, double sl, double tp, double atr, bool use_be)
  {
   // Resize array and add new trade
   int size = ArraySize(pendingTrades);
   ArrayResize(pendingTrades, size + 1);

   pendingTrades[size].unique_id = unique_id;
   pendingTrades[size].action = action;
   pendingTrades[size].entry = entry;
   pendingTrades[size].sl = sl;
   pendingTrades[size].tp = tp;
   pendingTrades[size].trade_time = TimeCurrent();

   // Calculate all market state features
   CalculateMarketFeatures(pendingTrades[size]);

   Print("Stored pending trade: ID=", unique_id, " Action=", action, " Edge Quality=", pendingTrades[size].edge_quality);
  }

//+------------------------------------------------------------------+
//| Extract Unique ID from Trade Comment                            |
//+------------------------------------------------------------------+
string ExtractUniqueIDFromComment(string comment)
  {
// Comment format: "DailyCB Scalper_B_1024_1430_0001"
   string prefix = m_comment + "_";

   int prefix_pos = StringFind(comment, prefix);
   if(prefix_pos == 0)
     {
      // Extract everything after the prefix
      string extracted = StringSubstr(comment, StringLen(prefix));
      Print("DEBUG: Extracted unique ID: '", extracted, "' from comment: '", comment, "'");
      return extracted;
     }

   Print("DEBUG: Prefix not found in comment: '", comment, "' (looking for: '", prefix, "')");
   return ""; // Return empty if not found
  }

//+------------------------------------------------------------------+
//| String conversion utility                                        |
//+------------------------------------------------------------------+
string BoolToStr(bool value)
  {
   if(value)
      return "true";
   return "false";
  }

//+------------------------------------------------------------------+
//| Find Original Unique ID from Position Opening Deal              |
//+------------------------------------------------------------------+
string FindOriginalUniqueID(ulong position_id)
  {
// Search through history to find the opening deal for this position
   if(HistorySelect(0, TimeCurrent()))
     {
      int total_deals = HistoryDealsTotal();

      for(int i = 0; i < total_deals; i++)
        {
         ulong deal_ticket = HistoryDealGetTicket(i);

         if(deal_ticket > 0)
           {
            ulong deal_position_id = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
            long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
            long deal_magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);

            // Found the opening deal for this position
            if(deal_position_id == position_id &&
               deal_entry == DEAL_ENTRY_IN &&
               deal_magic == magic_number)
              {
               string opening_comment = HistoryDealGetString(deal_ticket, DEAL_COMMENT);
               string unique_id = ExtractUniqueIDFromComment(opening_comment);

               if(unique_id != "")
                 {
                  Print("Found original unique ID: ", unique_id, " for position: ", position_id);
                  return unique_id;
                 }
              }
           }
        }
     }

   return ""; // Not found
  }

//+------------------------------------------------------------------+
//| Match Trade by Unique ID and Process                            |
//+------------------------------------------------------------------+
void MatchTradeByUniqueID(string unique_id, double exit_price, double profit)
  {
   Print("DEBUG: Looking for pending trade with ID: '", unique_id, "'");
   Print("DEBUG: Current pending trades count: ", ArraySize(pendingTrades));

// List all pending trades for debugging
   for(int k = 0; k < ArraySize(pendingTrades); k++)
     {
      Print("DEBUG: Pending trade [", k, "]: ID='", pendingTrades[k].unique_id, "'");
     }

// Find matching pending trade by unique ID
   for(int i = 0; i < ArraySize(pendingTrades); i++)
     {
      if(pendingTrades[i].unique_id == unique_id)
        {
         WriteCleanTrade(pendingTrades[i], exit_price, profit);

         // Remove processed trade from array
         for(int j = i; j < ArraySize(pendingTrades) - 1; j++)
           {
            pendingTrades[j] = pendingTrades[j + 1];
           }
         ArrayResize(pendingTrades, ArraySize(pendingTrades) - 1);
         Print("Trade matched and removed using Unique ID: ", unique_id);
         return;
        }
     }

   Print("WARNING: No pending trade found for Unique ID: ", unique_id);
  }

//+------------------------------------------------------------------+
//| Track closed positions and write complete trade data            |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
     {
      ulong deal_ticket = trans.deal;

      if(HistoryDealSelect(deal_ticket))
        {
         string symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
         double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
         double exit_price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
         long magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
         string comment = HistoryDealGetString(deal_ticket, DEAL_COMMENT);
         ulong position_id = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);

         if(magic == magic_number && profit != 0)
           {
            // First try to extract unique ID from comment
            string unique_id = ExtractUniqueIDFromComment(comment);

            if(unique_id != "")
              {
               // Direct match by unique ID
               MatchTradeByUniqueID(unique_id, exit_price, profit);
              }
            else
              {
               // Comment doesn't contain unique ID (e.g., "sl 2523.063")
               // Need to find the original position's opening deal to get the unique ID
               Print("Closing deal comment: ", comment, " - Searching for original position opening deal...");

               string original_unique_id = FindOriginalUniqueID(position_id);

               if(original_unique_id != "")
                 {
                  MatchTradeByUniqueID(original_unique_id, exit_price, profit);
                 }
               else
                 {
                  Print("ERROR: Could not find original unique ID for position: ", position_id);
                 }
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Write Complete Trade Data to Clean File                         |
//+------------------------------------------------------------------+
void WriteCleanTrade(PendingTrade &trade, double exit_price, double profit)
  {
   int fileHandle = FileOpen("clean_trades.csv", FILE_WRITE|FILE_READ|FILE_CSV, ';');
   if(fileHandle != INVALID_HANDLE)
     {
      // Check if file is empty (new file) to write header
      FileSeek(fileHandle, 0, SEEK_SET);
      bool isNewFile = (FileSize(fileHandle) == 0);
      
      if(isNewFile)
        {
         // Write header row
         string header = "";
         
         // TRADE IDENTIFICATION
         header += "Trade_Time;Symbol;Action;";
         
         // TRADE EXECUTION
         header += "Entry;Exit_Price;SL;TP;";
         
         // BREAKOUT QUALITY
         header += "Breakout_Strength;";
         
         // BREAKOUT TIME & SESSION
         header += "Hour_of_Day;Day_of_Week;Is_London_Session;Is_NY_Session;Is_Asian_Session;";
         
         // 7 H1 CANDLES BEFORE BREAKOUT (most recent to oldest)
         for(int i = 1; i <= 7; i++)
           {
            header += "C" + IntegerToString(i) + "_Open;";
            header += "C" + IntegerToString(i) + "_High;";
            header += "C" + IntegerToString(i) + "_Low;";
            header += "C" + IntegerToString(i) + "_Close;";
            header += "C" + IntegerToString(i) + "_BodyPts;";
            header += "C" + IntegerToString(i) + "_UpperWickPts;";
            header += "C" + IntegerToString(i) + "_LowerWickPts;";
           }
         
         // OUTCOMES
         header += "Win;Profit;Profit_Pct;Outcome";
         
         FileWriteString(fileHandle, header + "\n");
         Print("✅ CSV header written to clean_trades.csv");
        }
      
      FileSeek(fileHandle, 0, SEEK_END);

      // Determine outcome
      int win = (profit > 0) ? 1 : 0;
      string outcome = (profit > 0) ? "Win" : ((profit < 0) ? "Loss" : "Neutral");
      
      // Calculate profit percentage
      double profit_pct = (trade.entry > 0) ? (profit / trade.entry) * 100.0 : 0.0;

      // Build CSV row with new target-focused features
      string dataRow = "";
      
      // === TRADE IDENTIFICATION ===
      dataRow += TimeToString(trade.trade_time, TIME_DATE|TIME_MINUTES) + ";";
      dataRow += _Symbol + ";";
      dataRow += trade.action + ";";
      
      // === TRADE EXECUTION ===
      dataRow += DoubleToString(trade.entry, _Digits) + ";";
      dataRow += DoubleToString(exit_price, _Digits) + ";";
      dataRow += DoubleToString(trade.sl, _Digits) + ";";
      dataRow += DoubleToString(trade.tp, _Digits) + ";";

      // === KEEP: BREAKOUT QUALITY CORE ===
      dataRow += DoubleToString(trade.breakout_strength, 6) + ";"; // Breakout_Strength

      // === BREAKOUT TIME & SESSION META ===
      dataRow += IntegerToString(trade.hour_of_day) + ";";                 // Hour_of_Day
      dataRow += IntegerToString(trade.day_of_week) + ";";                 // Day_of_Week
      dataRow += IntegerToString(trade.is_london_session ? 1 : 0) + ";";   // Is_London_Session
      dataRow += IntegerToString(trade.is_ny_session ? 1 : 0) + ";";       // Is_NY_Session
      dataRow += IntegerToString(trade.is_asian_session ? 1 : 0) + ";";    // Is_Asian_Session

      // === NEW: 7 H1 CANDLES BEFORE BREAKOUT (OHLC + body/wicks in points) ===
      dataRow += BuildPreBreakoutCandlesCSV(trade.trade_time);
      
      // === OUTCOMES ===
      dataRow += IntegerToString(win) + ";";
      dataRow += DoubleToString(profit, 2) + ";";
      dataRow += DoubleToString(profit_pct, 4) + ";";
      dataRow += outcome;

      FileWriteString(fileHandle, dataRow + "\n");
      FileClose(fileHandle);

      Print("✅ Clean trade written: ID=", trade.unique_id, " Action=", trade.action, 
            " Profit=", profit, " Edge=", trade.edge_quality);
     }
   else
     {
      Print("❌ Failed to open file for writing. Error: ", GetLastError());
     }
  }

//+------------------------------------------------------------------+
void break_even()
  {
   if(PositionSelect(_Symbol) && m_position.Magic() == magic_number)
     {
      double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
        {
         if(currentPrice > entryPrice && entryPrice != currentSL)
           {
            double distanceToEntry = currentPrice - entryPrice;
            double slDistance = entryPrice - currentSL;

            if(distanceToEntry > slDistance)
               m_trade.PositionModify(_Symbol, entryPrice, PositionGetDouble(POSITION_TP));
           }
        }
      else
         if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
           {
            currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            if(currentPrice < entryPrice && entryPrice != currentSL)
              {
               double distanceToEntry = entryPrice - currentPrice;
               double slDistance = currentSL - entryPrice;

               if(distanceToEntry > slDistance)
                  m_trade.PositionModify(_Symbol, entryPrice, PositionGetDouble(POSITION_TP));
              }
           }
     }
  }
//+------------------------------------------------------------------+