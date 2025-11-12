//+------------------------------------------------------------------+
//|                                                  DailyCB_scalper |
//|                              Copyright 2024, Meffun Adegoke, TSA |
//+------------------------------------------------------------------+
#property copyright "Copyright 2024, Meffun Adegoke (Bot Dev), TSA"
#property link      "x.com/kingade_1"
#property version   "1.00"

#include <Trade\Trade.mqh> // Include MQL5 trading library

input double LotSize = 0.01;           // Fixed lot size
input int ATR_Period = 14;            // ATR period
input double ATR_Multiplier = 0.5;    // ATR multiplier for breakout buffer
input double SL_ATR_Multiplier = 1.0; // ATR multiplier for stop loss
input bool use_breakeven = true; // Use break even
input bool use_trailing_sl = true; // Use trailing stop loss (percentage-based)
input double trail_percent = 0.5; // Trailing stop percentage (0.5%)
input int magic_number = 307037;

CTrade m_trade;
CPositionInfo m_position;
int atrHandle;
double atrValue[];
bool allow_trade = false;
string m_comment = "DailyCB Scalper";

// Variables to store breakout levels
double upperBreakout = 0.0;
double lowerBreakout = 0.0;
datetime lastBreakoutTime = 0;
double bal;
double ini_bal;
const string TG_API_URL = "https://api.telegram.org";  // Base URL for Telegram API
string botTkn = "7614106788:AAH9qiT5URYNscIMeEFGwH2Gn_NiVePlsGA";  // Telegram bot token
string chatID = "6126141848";  // Chat ID for the Telegram chat
string user = "Ade";
string current_time;
string message;

// Initialization function
int OnInit()
  {
   m_trade.SetExpertMagicNumber(magic_number);
   m_trade.SetAsyncMode(true);
   m_trade.SetDeviationInPoints(30);
   ini_bal = AccountInfoDouble(ACCOUNT_BALANCE);
   current_time = TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES);
   message = StringFormat("DailyCB Scalper EA Initialized: User: %s, Symbol: %s, Account Balance: %s at %s",
                          user,_Symbol,DoubleToString(ini_bal,2), current_time);
   SendTelegramMessage(message);
// Create ATR handle
   atrHandle = iATR(_Symbol, PERIOD_D1, ATR_Period);
   if(atrHandle == INVALID_HANDLE)
     {
      Print("Error creating ATR handle. Code: ", _LastError);
      return(INIT_FAILED);
     }
   Print("DailyCB Scalper EA initialized successfully.");
   return(INIT_SUCCEEDED);
  }

//Function
void update_comment()
  {
   double curr_bal = AccountInfoDouble(ACCOUNT_BALANCE);
   if(bal != curr_bal)
     {
      double curr_profit = NormalizeDouble(curr_bal - ini_bal, 2);
      Comment("\nDailyCB Scalper \nAccount Balance: ", curr_bal,
              "\nCurrent Profit: ", curr_profit);
      bal = curr_bal;
     }
  }

// Deinitialization function
void OnDeinit(const int reason)
  {
   current_time = TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES);
   double final_bal = AccountInfoDouble(ACCOUNT_BALANCE);
   message = StringFormat("DailyCB Scalper EA Deinitialized: User: %s, Symbol: %s, Final Balance: %s at %s",
                          user,_Symbol,DoubleToString(final_bal,2), current_time);
   SendTelegramMessage(message);
   if(atrHandle != INVALID_HANDLE)
      IndicatorRelease(atrHandle);
  }

// Tick function
void OnTick()
  {
   update_comment();
   double curr_ask_price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double curr_bid_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   datetime currentDayTime = iTime(_Symbol, PERIOD_D1, 0);
   if(lastBreakoutTime != currentDayTime)
     {
      lastBreakoutTime = currentDayTime;

      double prevHigh = iHigh(_Symbol, PERIOD_D1, 1);
      double prevLow = iLow(_Symbol, PERIOD_D1, 1);

      if(CopyBuffer(atrHandle, 0, 0, 1, atrValue) <= 0)
        {
         Print("Error retrieving ATR value. Code: ", _LastError);
         return;
        }
      // Calculate breakout levels
      upperBreakout = prevHigh + (atrValue[0] * ATR_Multiplier);
      lowerBreakout = prevLow - (atrValue[0] * ATR_Multiplier);
      double levels[] = {lowerBreakout,upperBreakout};
      DrawRectangle(levels);

      double curr_daily_high = iHigh(_Symbol,PERIOD_D1,0);
      double curr_daily_low = iLow(_Symbol,PERIOD_D1,0);
      if(curr_daily_high > upperBreakout || curr_daily_low < lowerBreakout)
        {
         allow_trade = false;
         Print("Price already broken out before EA initialization, skipping trade for the day");
        }
      else
         allow_trade = true;
     }

   if(curr_bid_price > upperBreakout && allow_trade)
     {
      double stopLoss = NormalizeDouble(upperBreakout - (atrValue[0] * SL_ATR_Multiplier), _Digits);
      // No TP, will use trailing SL instead
      if(m_trade.Buy(LotSize, _Symbol, curr_ask_price, stopLoss, 0, m_comment))
        {
         allow_trade = false;
         current_time = TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES);
         message = StringFormat("DailyCB Scalper EA (%s): BUY position opened: Symbol: %s Price: %s at %s",
                                user,_Symbol,DoubleToString(curr_ask_price,_Digits), current_time);
         SendTelegramMessage(message);
        }
      else
         Print("Error placing buy order. Code: ", _LastError);
     }

   if(curr_bid_price < lowerBreakout && allow_trade)
     {
      double stopLoss = NormalizeDouble(lowerBreakout + (atrValue[0] * SL_ATR_Multiplier), _Digits);
      // No TP, will use trailing SL instead
      if(m_trade.Sell(LotSize, _Symbol, curr_bid_price, stopLoss, 0, m_comment))
        {
         allow_trade = false;
         current_time = TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES);
         message = StringFormat("DailyCB Scalper EA (%s): SELL position opened: Symbol: %s Price: %s at %s",
                                user,_Symbol,DoubleToString(curr_bid_price,_Digits), current_time);
         SendTelegramMessage(message);
        }
      else
         Print("Error placing sell order. Code: ", _LastError);
     }

   if(use_breakeven)
      break_even();
   
   if(use_trailing_sl)
      trailing_stop_loss();
  }

// Percentage-based trailing stop loss function
void trailing_stop_loss()
  {
   if(!PositionSelect(_Symbol))
      return;
      
   if(m_position.Magic() != magic_number)
      return;
   
   double currentSL = PositionGetDouble(POSITION_SL);
   double newSL = 0.0;
   
   if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
     {
      // For BUY: trail SL percentage behind current BID price
      double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      newSL = NormalizeDouble(currentPrice * (1 - trail_percent / 100.0), _Digits);
      
      // Only update if new SL is HIGHER than current SL (trailing up)
      if(newSL > currentSL)
        {
         if(m_trade.PositionModify(_Symbol, newSL, 0))
           {
            Print("✅ BUY Trailing SL updated: ", currentSL, " → ", newSL, 
                  " (", trail_percent, "% behind price: ", currentPrice, ")");
           }
         else
            Print("❌ Failed to update BUY trailing SL. Error: ", GetLastError());
        }
     }
   else if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
     {
      // For SELL: trail SL percentage above current ASK price
      double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      newSL = NormalizeDouble(currentPrice * (1 + trail_percent / 100.0), _Digits);
      
      // Only update if new SL is LOWER than current SL (trailing down)
      if(newSL < currentSL)
        {
         if(m_trade.PositionModify(_Symbol, newSL, 0))
           {
            Print("✅ SELL Trailing SL updated: ", currentSL, " → ", newSL, 
                  " (", trail_percent, "% above price: ", currentPrice, ")");
           }
         else
            Print("❌ Failed to update SELL trailing SL. Error: ", GetLastError());
        }
     }
  }

// break even function
void break_even()
  {
   if(PositionSelect(_Symbol) && m_position.Magic() == magic_number) // Ensure there is an open position
     {
      double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
        {
         // Only check if in profit
         if(currentPrice > entryPrice && entryPrice != currentSL)
           {
            double distanceToEntry = currentPrice - entryPrice;
            double slDistance = entryPrice - currentSL;

            if(distanceToEntry > slDistance) // Move SL to breakeven
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

// Method for sending alerts to telegram
void SendTelegramMessage(string msg)
  {
   char data[];  // Array to hold data to be sent in the web request (empty)
   char res[];  // Array to hold the response data from the web request
   string resHeaders;  // String to hold the response headers from the web request

// Construct the URL for the Telegram API request to send a message
// Format: https://api.telegram.org/bot{HTTP_API_TOKEN}/sendmessage?chat_id={CHAT_ID}&text={MESSAGE_TEXT}
   const string url = TG_API_URL + "/bot" + botTkn + "/sendmessage?chat_id=" + chatID +
                      "&text=" + msg;

// Check if the terminal is connected to the internet
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
     {
      //Print("NETWORK IS NOT CONNECTED, UNABLE TO SEND MESSAGE.");
      return;
     }

   if(StringLen(botTkn) == 0 || StringLen(chatID) == 0)   // Validate inputs
     {
      //Print("ERROR: Telegram bot token or chat ID is missing.");
      return;
     }

// Send the web request to the Telegram API
   int send_res = WebRequest("POST", url, "", 10000, data, res, resHeaders);
// Check the response status of the web request
   if(send_res == 200)
     {
      // If the response status is 200 (OK), print a success message
      //Print("ALERT SENT TO TELEGRAM SUCCESSFULLY");
     }
   else
      if(send_res == -1)
        {
         // If the response status is -1 (error), check the specific error code
         if(GetLastError() == 4014)
           {
            //// If the error code is 4014, it means the Telegram API URL is not allowed in the terminal
            //Print("PLEASE ADD THE ", TG_API_URL, " TO THE TERMINAL");
            //return;
           }
         //// Print a general error message if the request fails
         //Print("UNABLE TO SEND ALERT TO TELEGRAM");
         //return;
        }
      else
         if(send_res != 200)
           {
            // If the response status is not 200 or -1, print the unexpected response code and error code
            //Print("UNEXPECTED RESPONSE ", send_res, " ERR CODE = ", GetLastError());
            //return;
           }
  }

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void DrawRectangle(double &priceLevel[])
  {
   datetime priceTime = TimeCurrent();

// Delete all horizontal lines with prefix "Rectangle_"
   for(int i = ObjectsTotal(0) - 1; i >= 0; i--)
     {
      string objName = ObjectName(0, i);
      if(StringFind(objName, "Rectangle_") == 0)  // Check prefix
        {
         ObjectDelete(0, objName); // Delete object
        }
     }

   for(int i = 0; i < ArraySize(priceLevel); i++)
     {
      string rectangleName = StringFormat("Rectangle_%s_%f", _Symbol, priceLevel[i]);
      if(!ObjectCreate(0, rectangleName, OBJ_HLINE, 0, priceTime, priceLevel[i]))
        {
         Print("Failed to create rectangle. Error: ", GetLastError());
         return;
        }

      // Set line properties
      ObjectSetInteger(0, rectangleName, OBJPROP_COLOR, clrGold);          // Color based on level type
      ObjectSetInteger(0, rectangleName, OBJPROP_WIDTH, 1);                 // Line width
      ObjectSetInteger(0, rectangleName, OBJPROP_STYLE, STYLE_SOLID);       // Solid line
      ObjectSetInteger(0, rectangleName, OBJPROP_SELECTABLE, false);        // Non-selectable
      ObjectSetInteger(0, rectangleName, OBJPROP_HIDDEN, false);            // Visible on the chart
      ObjectSetInteger(0, rectangleName, OBJPROP_BACK, true);               // Drawn in the background
      ObjectSetInteger(0, rectangleName, OBJPROP_ZORDER, 0);                // Draw order
     }
  }
//+------------------------------------------------------------------+