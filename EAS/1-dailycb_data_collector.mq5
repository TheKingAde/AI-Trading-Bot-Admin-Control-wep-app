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
   string            unique_id;                    // Custom unique identifier (PRIMARY KEY)
   string            action;
   double            entry;
   double            sl;
   double            tp;
   datetime          trade_time;
   
   // === TIME-BASED FEATURES (Statistically Relevant) ===
  int               hour_of_day;                  // 0-23
  int               minutes_of_hour_of_day;       // 0-59
  int               time_to_next_session_open;    // Minutes until next session open
  int               time_from_current_session_open;// Minutes since current session open
  int               time_to_current_session_close;// Minutes until current session close
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
//| NOTE: BuildPreBreakoutCandlesCSV REMOVED                        |
//| We now focus only on time-based and economic calendar features  |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| Calculate Time + Economic Calendar Features (Simplified)        |
//+------------------------------------------------------------------+
void CalculateSimpleFeatures(PendingTrade &trade)
  {
   // === TIME FEATURES (Statistically Significant) ===
   MqlDateTime dt;
   TimeToStruct(trade.trade_time, dt);
   
   trade.hour_of_day = dt.hour;
   trade.minutes_of_hour_of_day = dt.min;
   int minutes_in_day = dt.hour * 60 + dt.min;
   // Session definitions (GMT): Asian 0:00-8:00, London 8:00-16:00, NY 13:00-21:00
   int asian_open = 0, asian_close = 8 * 60;
   int london_open = 8 * 60, london_close = 16 * 60;
   int ny_open = 13 * 60, ny_close = 21 * 60;

   // Default: not in any session
   trade.time_to_next_session_open = 0;
   trade.time_from_current_session_open = 0;
   trade.time_to_current_session_close = 0;

   // Asian session
   if(minutes_in_day >= asian_open && minutes_in_day < asian_close)
     {
       trade.time_to_next_session_open = 0;
       trade.time_from_current_session_open = minutes_in_day - asian_open;
       trade.time_to_current_session_close = asian_close - minutes_in_day;
     }
   // London session
   else if(minutes_in_day >= london_open && minutes_in_day < london_close)
     {
       trade.time_to_next_session_open = 0;
       trade.time_from_current_session_open = minutes_in_day - london_open;
       trade.time_to_current_session_close = london_close - minutes_in_day;
     }
   // NY session
   else if(minutes_in_day >= ny_open && minutes_in_day < ny_close)
     {
       trade.time_to_next_session_open = 0;
       trade.time_from_current_session_open = minutes_in_day - ny_open;
       trade.time_to_current_session_close = ny_close - minutes_in_day;
     }
   else
     {
       // Not in any session, calculate time to next session open
       int next_open = asian_open;
       if(minutes_in_day < asian_open)
         next_open = asian_open;
       else if(minutes_in_day < london_open)
         next_open = london_open;
       else if(minutes_in_day < ny_open)
         next_open = ny_open;
       else
         next_open = 24 * 60; // Next day Asian session
       trade.time_to_next_session_open = next_open - minutes_in_day;
       trade.time_from_current_session_open = 0;
       trade.time_to_current_session_close = 0;
     }
   
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

   // Calculate simple time + economic features
   CalculateSimpleFeatures(pendingTrades[size]);

   Print("Stored pending trade: ID=", unique_id, " Action=", action, " Hour=", pendingTrades[size].hour_of_day);
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
//| Write Complete Trade Data to Clean File (SIMPLIFIED SCHEMA)     |
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
          // === NEW MINIMAL HEADER ===
          string header = "";
          header += "Trade_Time;Symbol;Action;Entry;Exit_Price;SL;TP;";
          header += "Hour_of_Day;Minutes_of_Hour_of_Day;Time_To_Next_Session_Open;Time_From_Current_Session_Open;Time_to_Current_Session_Close;";
          header += "Win;Profit;Profit_Pct;Outcome";
         
         FileWriteString(fileHandle, header + "\n");
         Print("✅ NEW SIMPLIFIED CSV header written to clean_trades.csv");
        }
      
      FileSeek(fileHandle, 0, SEEK_END);

      // Determine outcome
      int win = (profit > 0) ? 1 : 0;
      string outcome = (profit > 0) ? "Win" : ((profit < 0) ? "Loss" : "Neutral");
      double profit_pct = (trade.entry > 0) ? (profit / trade.entry) * 100.0 : 0.0;

      // === BUILD CSV ROW ===
      string dataRow = "";
      
        // TRADE ID & EXECUTION
        dataRow += TimeToString(trade.trade_time, TIME_DATE|TIME_MINUTES) + ";";
        dataRow += _Symbol + ";";
        dataRow += trade.action + ";";
        dataRow += DoubleToString(trade.entry, _Digits) + ";";
        dataRow += DoubleToString(exit_price, _Digits) + ";";
        dataRow += DoubleToString(trade.sl, _Digits) + ";";
        dataRow += DoubleToString(trade.tp, _Digits) + ";";
        // TIME FEATURES ONLY
  dataRow += IntegerToString(trade.hour_of_day) + ";";
  dataRow += IntegerToString(trade.minutes_of_hour_of_day) + ";";
  dataRow += IntegerToString(trade.time_to_next_session_open) + ";";
  dataRow += IntegerToString(trade.time_from_current_session_open) + ";";
  dataRow += IntegerToString(trade.time_to_current_session_close) + ";";
        // OUTCOMES
        dataRow += IntegerToString(win) + ";";
        dataRow += DoubleToString(profit, 2) + ";";
        dataRow += DoubleToString(profit_pct, 4) + ";";
        dataRow += outcome;
      
    
      // OUTCOMES
      dataRow += IntegerToString(win) + ";";
      dataRow += DoubleToString(profit, 2) + ";";
      dataRow += DoubleToString(profit_pct, 4) + ";";
      dataRow += outcome;

      FileWriteString(fileHandle, dataRow + "\n");
      FileClose(fileHandle);

      Print("✅ Trade written: ID=", trade.unique_id, " Hour=", trade.hour_of_day, 
            " Profit=", profit);
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