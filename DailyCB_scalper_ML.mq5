//+------------------------------------------------------------------+
//|                                                  DailyCB_scalper |
//|                              Copyright 2024, Meffun Adegoke, TSA |
//+------------------------------------------------------------------+
#property copyright "Copyright 2024, Meffun Adegoke (Bot Dev), TSA"
#property link      "x.com/kingade_1"
#property version   "1.00"

#include <Trade\Trade.mqh> // Include MQL5 trading library

input string user = "Ade"; // Replace with your name
input double LotSize = 0.01;           // Fixed lot size
input int ATR_Period = 14;            // ATR period
input double ATR_Multiplier = 0.5;    // ATR multiplier for breakout buffer
input double SL_ATR_Multiplier = 1.0; // ATR multiplier for stop loss
input double TP_ATR_Multiplier = 2.0; // ATR multiplier for take profit
input bool use_breakeven = true; // Use break even
input int magic_number = 307037; // Magic number

CTrade m_trade;
CPositionInfo m_position;
int atrHandle;
int emaHandle;
int rsiHandle;
double atrValue[];
bool allow_buy_trade = true;
bool allow_sell_trade = true;
string m_comment = "DailyCB Scalper";

// Variables to store breakout levels
double upperBreakout = 0.0;
double lowerBreakout = 0.0;
datetime lastBreakoutTime = 0;
double bal;
double ini_bal;
const string TG_API_URL = "https://api.telegram.org";  // Base URL for Telegram API
string botTkn = "7969763015:AAEliO2m1l9Yn7dDY8j_PKvG3_4yHlXbuZY";  // Telegram bot token
string chatID = "6126141848";  // Chat ID for the Telegram chat
string current_time;
string message;
string admin_url = "http://16.171.169.239:3000";
datetime expiry_date;
input long license_key = 12345; // license key
bool license_status = false;
string license_name = "";

// ML Model integration variables
string pending_trade_id = "";  // Store trade_id from model response
double pending_entry_price = 0.0;
datetime pending_entry_time = 0;


// Function to send account data to backend
bool SendAccountData()
  {
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

   string url = admin_url + "/api/account_data";

// Create JSON payload
   string payload = StringFormat("{\"license_key\":\"%d\",\"balance\":%.2f,\"equity\":%.2f}",
                                 license_key, balance, equity);

   char post_data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   StringToCharArray(payload, post_data, 0, StringLen(payload));

   ResetLastError();

   int res = WebRequest("POST", url, headers, 5000, post_data, result, headers);

   if(res == -1)
     {
      int error = GetLastError();
      if(error == 4060)
        {
         Print("ERROR: WebRequest not allowed. Add URL to Tools->Options->Expert Advisors->Allow WebRequest for listed URLs:");
         Print("Add: ", admin_url);
        }
      else
        {
         Print("WebRequest error sending account data: ", error);
        }
      return false;
     }

   if(res == 200)
     {
      string response = CharArrayToString(result);
      Print("Account data sent successfully: ", response);
      return true;
     }
   else
     {
      Print("ERROR: Server returned status code: ", res);
      string response = CharArrayToString(result);
      Print("Server response: ", response);
      return false;
     }
  }
// Function to get closed trade history and send to backend
bool SendTradeHistory()
  {
   HistorySelect(0, TimeCurrent()); // Select all history

   int total_deals = HistoryDealsTotal();

// Build JSON array of trades
   string trades_json = "[";
   int trade_count = 0;

   for(int i = 0; i < total_deals; i++)
     {
      ulong deal_ticket = HistoryDealGetTicket(i);

      if(deal_ticket > 0)
        {
         // Only process deals from this EA (matching magic number)
         if(HistoryDealGetInteger(deal_ticket, DEAL_MAGIC) == magic_number)
           {
            // Only process OUT deals (closed positions)
            ENUM_DEAL_ENTRY entry_type = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
            if(entry_type == DEAL_ENTRY_OUT)
              {
               string symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
               double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
               double lots = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
               datetime time_close = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);
               ENUM_DEAL_TYPE deal_type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(deal_ticket, DEAL_TYPE);

               // Get corresponding position to find open time
               ulong position_id = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
               datetime time_open = 0;

               // Find the IN deal for this position
               for(int j = 0; j < total_deals; j++)
                 {
                  ulong in_deal = HistoryDealGetTicket(j);
                  if(HistoryDealGetInteger(in_deal, DEAL_POSITION_ID) == position_id)
                    {
                     ENUM_DEAL_ENTRY in_entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(in_deal, DEAL_ENTRY);
                     if(in_entry == DEAL_ENTRY_IN)
                       {
                        time_open = (datetime)HistoryDealGetInteger(in_deal, DEAL_TIME);
                        break;
                       }
                    }
                 }

               // Determine position type (BUY or SELL)
               string position_type = "";
               if(deal_type == DEAL_TYPE_BUY)
                  position_type = "SELL"; // Closing a sell position
               else
                  if(deal_type == DEAL_TYPE_SELL)
                     position_type = "BUY"; // Closing a buy position

               // Format timestamps for backend (YYYY-MM-DD HH:MM:SS)
               string time_open_str = TimeToString(time_open, TIME_DATE | TIME_SECONDS);
               StringReplace(time_open_str, ".", "-");

               string time_close_str = TimeToString(time_close, TIME_DATE | TIME_SECONDS);
               StringReplace(time_close_str, ".", "-");

               // Add comma separator if not first trade
               if(trade_count > 0)
                  trades_json += ",";

               // Build trade JSON object
               trades_json += StringFormat("{\"symbol\":\"%s\",\"type\":\"%s\",\"lots\":%.2f,\"profit\":%.2f,\"time_open\":\"%s\",\"time_close\":\"%s\"}",
                                           symbol, position_type, lots, profit, time_open_str, time_close_str);

               trade_count++;
              }
           }
        }
     }

   trades_json += "]";

   if(trade_count == 0)
     {
      Print("No closed trades found for magic number: ", magic_number);
      return true; // Not an error, just no trades yet
     }

// Send to backend
   string url = admin_url + "/api/trade_history";

   string payload = StringFormat("{\"license_key\":\"%d\",\"trades\":%s}",
                                 license_key, trades_json);

   char post_data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";

   StringToCharArray(payload, post_data, 0, StringLen(payload));

   ResetLastError();

   int res = WebRequest("POST", url, headers, 5000, post_data, result, headers);

   if(res == -1)
     {
      int error = GetLastError();
      if(error == 4060)
        {
         Print("ERROR: WebRequest not allowed. Add URL to Tools->Options->Expert Advisors->Allow WebRequest for listed URLs:");
         Print("Add: ", admin_url);
        }
      else
        {
         Print("WebRequest error sending trade history: ", error);
        }
      return false;
     }

   if(res == 200)
     {
      string response = CharArrayToString(result);
      Print("Trade history sent successfully: ", trade_count, " trades. Server response: ", response);
      return true;
     }
   else
     {
      Print("ERROR: Server returned status code: ", res);
      string response = CharArrayToString(result);
      Print("Server response: ", response);
      return false;
     }
  }
//+------------------------------------------------------------------+
bool CheckLicense()
  {
   string url = admin_url + "/api/license/check?key=" + IntegerToString(license_key);

   char data[];
   char result[];
   string headers = "";

   ResetLastError();

   int res = WebRequest("GET", url, headers, 5000, data, result, headers);

   if(res == -1)
     {
      int error = GetLastError();
      if(error == 4060)
        {
         Print("ERROR: WebRequest not allowed. Add URL to Tools->Options->Expert Advisors->Allow WebRequest for listed URLs:");
         Print("Add: ", admin_url);
        }
      else
        {
         Print("WebRequest error: ", error);
        }
      return false;
     }

   if(res == 200)
     {
      string response = CharArrayToString(result);
      Print("License check response: ", response);

      // Parse key
      int key_pos = StringFind(response, "key=");
      int key_end = StringFind(response, ";", key_pos);
      string key_val = (key_pos >= 0 && key_end > key_pos) ? StringSubstr(response, key_pos+4, key_end-key_pos-4) : "";

      // Parse status
      int status_pos = StringFind(response, "status=");
      int status_end = StringFind(response, ";", status_pos);
      string status_val = (status_pos >= 0 && status_end > status_pos) ? StringSubstr(response, status_pos+7, status_end-status_pos-7) : "";

      // Parse name
      int name_pos = StringFind(response, "name=");
      int name_end = StringFind(response, ";", name_pos);
      string name_val = (name_pos >= 0 && name_end > name_pos) ? StringSubstr(response, name_pos+5, name_end-name_pos-5) : "";

      // Parse expires_at
      int exp_pos = StringFind(response, "expires_at=");
      string exp_val = "";
      if(exp_pos >= 0)
        {
         exp_val = StringSubstr(response, exp_pos+11);
         int semi = StringFind(exp_val, ";");
         if(semi >= 0)
            exp_val = StringSubstr(exp_val, 0, semi);
         if(exp_val != "")
           {
            string clean_exp = exp_val;

            exp_val = clean_exp + ":00";
           }
        }

      license_status = (status_val == "active");
      license_name = name_val;

      // Parse expiry date
      expiry_date = StringToTime(exp_val);
      Print("License expires at: ", exp_val, " (parsed: ", TimeToString(expiry_date, TIME_DATE | TIME_MINUTES), ")");
      Print("License holder: ", license_name);

      if(license_status && TimeCurrent() < expiry_date)
        {
         Print("License validated successfully!");
         return true;
        }
      else
        {
         Print("ERROR: License is not active or expired.");
         return false;
        }

     }
   else
      if(res == 404)
        {
         Print("ERROR: License key not found (404)");
         return false;
        }
      else
        {
         Print("ERROR: Server returned status code: ", res);
         return false;
        }

   return false;
  }

// ==================== ML MODEL FEATURE CALCULATION ====================
// Calculate all 21 features required by the model
bool CalculateModelFeatures(int action, double &features[])
  {
   ArrayResize(features, 21);
   
   // Feature 0: Symbol (0 for current symbol as single-instrument model)
   features[0] = 0;
   
   // Feature 1: Action (0=SELL, 1=BUY)
   features[1] = action;
   
   // Get ATR value
   double atr[];
   if(CopyBuffer(atrHandle, 0, 0, 1, atr) <= 0)
     {
      Print("Error getting ATR value");
      return false;
     }
   
   // Feature 2: ATR_rel (ATR relative to current price)
   double curr_price = (action == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   features[2] = atr[0] / curr_price;
   
   // Get EMA value
   double ema[];
   if(CopyBuffer(emaHandle, 0, 0, 1, ema) <= 0)
     {
      Print("Error getting EMA value");
      return false;
     }
   
   // Feature 3: EMA_diff (price relative to EMA)
   features[3] = (curr_price - ema[0]) / curr_price;
   
   // Get RSI value
   double rsi[];
   if(CopyBuffer(rsiHandle, 0, 0, 1, rsi) <= 0)
     {
      Print("Error getting RSI value");
      return false;
     }
   
   // Feature 4: RSI14
   features[4] = rsi[0];
   
   // Get recent candle data for range calculations
   double high[], low[], open[], close[];
   if(CopyHigh(_Symbol, PERIOD_D1, 0, 30, high) <= 0 ||
      CopyLow(_Symbol, PERIOD_D1, 0, 30, low) <= 0 ||
      CopyOpen(_Symbol, PERIOD_D1, 0, 30, open) <= 0 ||
      CopyClose(_Symbol, PERIOD_D1, 0, 30, close) <= 0)
     {
      Print("Error getting candle data");
      return false;
     }
   
   // Feature 5: Range_Ratio (current range vs average range)
   double curr_range = high[0] - low[0];
   double avg_range = 0;
   for(int i = 1; i < 30; i++)
      avg_range += (high[i] - low[i]);
   avg_range /= 29;
   features[5] = (avg_range > 0) ? curr_range / avg_range : 1.0;
   
   // Get 30-period high and low
   double high_30 = high[ArrayMaximum(high, 0, 30)];
   double low_30 = low[ArrayMinimum(low, 0, 30)];
   
   // Feature 6: Pct_from_30h (distance from 30-bar high)
   features[6] = (high_30 > 0) ? (curr_price - high_30) / high_30 : 0;
   
   // Feature 7: Pct_from_30l (distance from 30-bar low)
   features[7] = (low_30 > 0) ? (curr_price - low_30) / low_30 : 0;
   
   // Feature 8: Breakout_level_atr_multiplier (using ATR_Multiplier from inputs)
   features[8] = ATR_Multiplier;
   
   // Feature 9: SL_ATR_Mult
   features[9] = SL_ATR_Multiplier;
   
   // Feature 10: TP_ATR_Mult
   features[10] = TP_ATR_Multiplier;
   
   // Feature 11: Use_BE (breakeven setting)
   features[11] = use_breakeven ? 1 : 0;
   
   // Feature 12: Risk_Reward_Ratio
   features[12] = TP_ATR_Multiplier / SL_ATR_Multiplier;
   
   // Feature 13: High_Volatility (1 if ATR > recent average)
   double atr_history[];
   if(CopyBuffer(atrHandle, 0, 0, 14, atr_history) > 0)
     {
      double avg_atr = 0;
      for(int i = 1; i < 14; i++)
         avg_atr += atr_history[i];
      avg_atr /= 13;
      features[13] = (atr[0] > avg_atr) ? 1 : 0;
     }
   else
      features[13] = 0;
   
   // Feature 14: Day_of_Week (0=Sunday, 1=Monday, ..., 6=Saturday)
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   features[14] = dt.day_of_week;
   
   // Feature 15: Consecutive_Bullish (count recent bullish candles)
   int bullish_count = 0;
   for(int i = 1; i < 10 && i < ArraySize(close); i++)
     {
      if(close[i] > open[i])
         bullish_count++;
      else
         break;
     }
   features[15] = bullish_count;
   
   // Feature 16: Consecutive_Bearish (count recent bearish candles)
   int bearish_count = 0;
   for(int i = 1; i < 10 && i < ArraySize(close); i++)
     {
      if(close[i] < open[i])
         bearish_count++;
      else
         break;
     }
   features[16] = bearish_count;
   
   // Feature 17: Avg_Body_Size (average candle body size)
   double avg_body = 0;
   for(int i = 1; i < 20 && i < ArraySize(close); i++)
      avg_body += MathAbs(close[i] - open[i]);
   features[17] = (avg_body > 0) ? avg_body / MathMin(19, ArraySize(close)-1) : 0;
   
   // Feature 18: Avg_Range (already calculated above)
   features[18] = avg_range;
   
   // Feature 19: Trend_Score (EMA slope approximation)
   double ema_history[];
   if(CopyBuffer(emaHandle, 0, 0, 5, ema_history) > 0 && ArraySize(ema_history) >= 5)
     {
      double ema_slope = (ema_history[0] - ema_history[4]) / ema_history[4];
      features[19] = ema_slope;
     }
   else
      features[19] = 0;
   
   // Feature 20: Momentum_Strength (rate of price change)
   if(ArraySize(close) >= 10)
     {
      double momentum = (close[0] - close[9]) / close[9];
      features[20] = momentum;
     }
   else
      features[20] = 0;
   
   return true;
  }

// Send features to ML model and get decision
bool GetModelDecision(double &features[], string &trade_id_out, double &probability_out)
  {
   string url = admin_url + "/api/entry-decision";
   string headers = "Content-Type: application/json\r\n";
   
   // Build JSON payload with features array
   string json = "{\"features\":[";
   for(int i = 0; i < 21; i++)
     {
      json += DoubleToString(features[i], 8);
      if(i < 20) json += ",";
     }
   json += "]}";
   
   char post_data[];
   char result_data[];
   string result_headers;
   
   StringToCharArray(json, post_data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(post_data, ArraySize(post_data) - 1);
   
   int res = WebRequest("POST", url, headers, 5000, post_data, result_data, result_headers);
   
   if(res != 200)
     {
      Print("ML Model request failed. Error code: ", res);
      return false;
     }
   
   string response = CharArrayToString(result_data);
   Print("ML Model response: ", response);
   
   // Parse JSON response (simple parsing for: {"enter":1,"probability":0.75,"confidence":0.5,"threshold":0.7,"trade_id":"..."})
   int enter_pos = StringFind(response, "\"enter\":");
   int prob_pos = StringFind(response, "\"probability\":");
   int trade_id_pos = StringFind(response, "\"trade_id\":\"");
   
   if(enter_pos < 0 || prob_pos < 0 || trade_id_pos < 0)
     {
      Print("Failed to parse model response");
      return false;
     }
   
   // Extract enter value
   string enter_str = StringSubstr(response, enter_pos + 8, 1);
   int enter_value = (int)StringToInteger(enter_str);
   
   // Extract probability
   string prob_substr = StringSubstr(response, prob_pos + 15);
   int prob_end = StringFind(prob_substr, ",");
   if(prob_end > 0)
     {
      string prob_str = StringSubstr(prob_substr, 0, prob_end);
      probability_out = StringToDouble(prob_str);
     }
   
   // Extract trade_id
   string trade_id_substr = StringSubstr(response, trade_id_pos + 12);
   int trade_id_end = StringFind(trade_id_substr, "\"");
   if(trade_id_end > 0)
      trade_id_out = StringSubstr(trade_id_substr, 0, trade_id_end);
   
   Print("Model decision: enter=", enter_value, ", probability=", probability_out, ", trade_id=", trade_id_out);
   
   return (enter_value == 1);
  }

// Update trade outcome after close
bool UpdateTradeOutcome(string trade_id, double profit, string outcome)
  {
   string url = admin_url + "/api/entry-update";
   string headers = "Content-Type: application/json\r\n";
   
   int profitable = (profit > 0) ? 1 : 0;
   
   string json = StringFormat("{\"trade_id\":\"%s\",\"Profitable\":%d,\"Final_PnL\":%.2f,\"Outcome_Category\":\"%s\"}",
                              trade_id, profitable, profit, outcome);
   
   char post_data[];
   char result_data[];
   string result_headers;
   
   StringToCharArray(json, post_data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(post_data, ArraySize(post_data) - 1);
   
   int res = WebRequest("POST", url, headers, 5000, post_data, result_data, result_headers);
   
   if(res == 200)
     {
      Print("Trade outcome updated successfully for trade_id: ", trade_id);
      return true;
     }
   else
     {
      Print("Failed to update trade outcome. Error code: ", res);
      return false;
     }
  }

// Initialization function
int OnInit()
  {
// Check license first
   Print("Checking license key: ", license_key);
   Print(AccountInfoDouble(ACCOUNT_PROFIT));
   if(!CheckLicense())
     {
      Print("LICENSE VALIDATION FAILED! EA will not run.");
      Print("Please contact support on X @Kingade_1");
      return(INIT_FAILED);
     }

   Print("License valid for: ", license_name);
   Print("Days remaining: ", (int)((expiry_date - TimeCurrent()) / 86400));
   if(!SendAccountData())
     {
      Print("Warning: Failed to send initial account data to server");
     }
   SendTradeHistory();
// Continue with normal initialization
   m_trade.SetExpertMagicNumber(magic_number);
   m_trade.SetAsyncMode(true);
   m_trade.SetDeviationInPoints(30);
   ini_bal = AccountInfoDouble(ACCOUNT_BALANCE);
   bal = ini_bal;
   current_time = TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES);
   message = StringFormat("DailyCB Initialized: User: %s (%s), Symbol: %s, Account Balance: %s at %s",
                          license_name, user, _Symbol, IntegerToString(ini_bal), current_time);
   SendTelegramMessage(message);
// Create ATR handle
   atrHandle = iATR(_Symbol, PERIOD_D1, ATR_Period);
   if(atrHandle == INVALID_HANDLE)
     {
      Print("Error creating ATR handle. Code: ", _LastError);
      return(INIT_FAILED);
     }
   
   // Create EMA handle (200-period for trend)
   emaHandle = iMA(_Symbol, PERIOD_D1, 200, 0, MODE_EMA, PRICE_CLOSE);
   if(emaHandle == INVALID_HANDLE)
     {
      Print("Error creating EMA handle. Code: ", _LastError);
      return(INIT_FAILED);
     }
   
   // Create RSI handle
   rsiHandle = iRSI(_Symbol, PERIOD_D1, 14, PRICE_CLOSE);
   if(rsiHandle == INVALID_HANDLE)
     {
      Print("Error creating RSI handle. Code: ", _LastError);
      return(INIT_FAILED);
     }

   Print("DailyCB initialized successfully with ML model integration.");
   EventSetTimer(30);
   return(INIT_SUCCEEDED);
  }

//Function
void update_comment()
  {
   double curr_bal = AccountInfoDouble(ACCOUNT_BALANCE);
   Comment("\n",m_comment,"\nAccount Balance: ", AccountInfoDouble(ACCOUNT_BALANCE),
           "\nCurrent Profit: ", AccountInfoDouble(ACCOUNT_PROFIT));
  }

// Deinitialization function
void OnDeinit(const int reason)
  {
   current_time = TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES);
   message = StringFormat("DailyCB Deinitialized: User: %s, Symbol: %s, Account Balance: %s at %s",
                          user,_Symbol,IntegerToString(bal), current_time);
   SendTelegramMessage(message);
   if(atrHandle != INVALID_HANDLE)
      IndicatorRelease(atrHandle);
   if(emaHandle != INVALID_HANDLE)
      IndicatorRelease(emaHandle);
   if(rsiHandle != INVALID_HANDLE)
      IndicatorRelease(rsiHandle);
  }

//+------------------------------------------------------------------+
int retry_no = 0;
void OnTimer()
  {
   if(!CheckLicense())
     {
      Print("LICENSE VALIDATION FAILED");
      Print("Please contact support on X @Kingade_1");
      if(retry_no >= 3)
         ExpertRemove();
      else
         retry_no++;
     }
   else
      retry_no = 0;

   if(!SendAccountData())
     {
      Print("Warning: Failed to send initial account data to server");
     }
  }

//+------------------------------------------------------------------+
//|                                                                  |
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
         long magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
         long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
         double lots = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
         ENUM_DEAL_TYPE deal_type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(deal_ticket, DEAL_TYPE);
         datetime time_deal = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);

         if(magic == magic_number)
           {
            string trade_type = "";
            string status = "";

            // Determine if this is an entry (open) or exit (close)
            if(entry == DEAL_ENTRY_IN)
              {
               // Trade is being opened
               status = "open";
               profit = 0.0; // Profit is 0 when opening
               // Determine trade direction
               if(deal_type == DEAL_TYPE_BUY)
                  trade_type = "BUY";
               else
                  if(deal_type == DEAL_TYPE_SELL)
                     trade_type = "SELL";
                  else
                     return;
              }
            else
               if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
                 {
                  // Trade is being closed - update outcome
                  status = "closed";
                  // Determine trade direction
                  if(deal_type == DEAL_TYPE_BUY)
                     trade_type = "SELL";
                  else
                     if(deal_type == DEAL_TYPE_SELL)
                        trade_type = "BUY";
                     else
                        return;
                  
                  // Update ML model with trade outcome
                  if(pending_trade_id != "")
                    {
                     string outcome = (profit > 0) ? "Win" : "Loss";
                     UpdateTradeOutcome(pending_trade_id, profit, outcome);
                     pending_trade_id = ""; // Reset after update
                    }
                 }
               else
                 {
                  return; // Skip other entry types
                 }

            // Get the position open time
            datetime time_open = time_deal;
            datetime time_close = NULL;

            if(status == "closed")
              {
               // For closed trades, we need to find the original open time
               // Search through position history to find the matching entry
               if(HistorySelectByPosition(trans.position))
                 {
                  int deals_total = HistoryDealsTotal();
                  for(int i = 0; i < deals_total; i++)
                    {
                     ulong deal = HistoryDealGetTicket(i);
                     if(HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_IN &&
                        HistoryDealGetInteger(deal, DEAL_MAGIC) == magic_number)
                       {
                        time_open = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
                        break;
                       }
                    }
                 }
               time_close = time_deal;
              }

            // Send trade data to API (for dashboard tracking)
            SendTradeData(symbol, lots, trade_type, profit, time_open, time_close, status);
           }
        }
     }
  }

// Helper function to send trade data to the API
void SendTradeData(string symbol, double lots, string trade_type, double profit,
                   datetime time_open, datetime time_close, string status)
  {
   string url = admin_url + "/api/trade_history";
   string headers = "Content-Type: application/json\r\n";

   char post_data[];
   char result_data[];
   string result_headers;

// Format datetime to ISO format for the API
   string time_open_str = TimeToString(time_open, TIME_DATE|TIME_MINUTES|TIME_SECONDS);
   StringReplace(time_open_str, ".", "-");
   time_open_str = time_open_str + "Z";

   string time_close_str = "";
   if(time_close > 0)
     {
      time_close_str = TimeToString(time_close, TIME_DATE|TIME_MINUTES|TIME_SECONDS);
      StringReplace(time_close_str, ".", "-");
      time_close_str = time_close_str + "Z";
     }

// Build JSON payload
   string json = "{";
   json += "\"license_key\":\"" + license_key + "\",";
   json += "\"trades\":[{";
   json += "\"symbol\":\"" + symbol + "\",";
   json += "\"lots\":" + DoubleToString(lots, 2) + ",";
   json += "\"type\":\"" + trade_type + "\",";
   json += "\"profit\":" + DoubleToString(profit, 2) + ",";
   json += "\"time_open\":\"" + time_open_str + "\",";
   json += "\"time_close\":\"" + (time_close > 0 ? time_close_str : "null") + "\",";
   json += "\"status\":\"" + status + "\"";
   json += "}]}";

   StringToCharArray(json, post_data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(post_data, ArraySize(post_data) - 1); // Remove null terminator

   int res = WebRequest("POST", url, headers, 5000, post_data, result_data, result_headers);

   if(res == 200)
     {
      Print("Trade data sent successfully: ", symbol, " ", status, " Profit: ", profit);
     }
   else
     {
      Print("Failed to send trade data. Error code: ", res);
     }
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
      double prevLow  = iLow(_Symbol, PERIOD_D1, 1);

      if(CopyBuffer(atrHandle, 0, 0, 1, atrValue) <= 0)
        {
         Print("Error retrieving ATR value. Code: ", _LastError);
         return;
        }

      upperBreakout = prevHigh + (atrValue[0] * ATR_Multiplier);
      lowerBreakout = prevLow  - (atrValue[0] * ATR_Multiplier);
      double levels[] = {lowerBreakout, upperBreakout};
      DrawRectangle(levels);

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

// ✅ BUY condition with ML model confirmation
   if(curr_ask_price > upperBreakout && allow_buy_trade)
     {
      // Calculate features for BUY action
      double features[];
      if(!CalculateModelFeatures(1, features)) // 1 = BUY
        {
         Print("Failed to calculate features for BUY");
         return;
        }
      
      // Get ML model decision
      string trade_id;
      double probability;
      bool model_approved = GetModelDecision(features, trade_id, probability);
      
      if(!model_approved)
        {
         Print("ML Model rejected BUY trade. Probability: ", probability);
         allow_buy_trade = false; // Prevent retry on same breakout
         return;
        }
      
      Print("ML Model approved BUY trade. Probability: ", probability);
      
      double stopLoss   = NormalizeDouble(upperBreakout - (atrValue[0] * SL_ATR_Multiplier), _Digits);
      double takeProfit = NormalizeDouble(upperBreakout + (atrValue[0] * TP_ATR_Multiplier), _Digits);

      if(m_trade.Buy(LotSize, _Symbol, 0.0, stopLoss, takeProfit, m_comment))
        {
         // Store trade_id for later outcome update
         pending_trade_id = trade_id;
         pending_entry_price = curr_ask_price;
         pending_entry_time = TimeCurrent();
         
         allow_buy_trade = false;
         allow_sell_trade = false; // ensure only one trade per day
         message = StringFormat("DailyCB: ML-Approved Buy Position Opened. Pair: %s, Probability: %.2f%%", _Symbol, probability * 100);
         SendTelegramMessage(message);
        }
      else
         Print("Error placing buy order. Code: ", _LastError);
     }

// ✅ SELL condition with ML model confirmation
   if(curr_bid_price < lowerBreakout && allow_sell_trade)
     {
      // Calculate features for SELL action
      double features[];
      if(!CalculateModelFeatures(0, features)) // 0 = SELL
        {
         Print("Failed to calculate features for SELL");
         return;
        }
      
      // Get ML model decision
      string trade_id;
      double probability;
      bool model_approved = GetModelDecision(features, trade_id, probability);
      
      if(!model_approved)
        {
         Print("ML Model rejected SELL trade. Probability: ", probability);
         allow_sell_trade = false; // Prevent retry on same breakout
         return;
        }
      
      Print("ML Model approved SELL trade. Probability: ", probability);
      
      double stopLoss   = NormalizeDouble(lowerBreakout + (atrValue[0] * SL_ATR_Multiplier), _Digits);
      double takeProfit = NormalizeDouble(lowerBreakout - (atrValue[0] * TP_ATR_Multiplier), _Digits);

      if(m_trade.Sell(LotSize, _Symbol, 0.0, stopLoss, takeProfit, m_comment))
        {
         // Store trade_id for later outcome update
         pending_trade_id = trade_id;
         pending_entry_price = curr_bid_price;
         pending_entry_time = TimeCurrent();
         
         allow_buy_trade = false;
         allow_sell_trade = false; // ensure only one trade per day
         message = StringFormat("DailyCB: ML-Approved Sell Position Opened. Pair: %s, Probability: %.2f%%", _Symbol, probability * 100);
         SendTelegramMessage(message);
        }
      else
         Print("Error placing sell order. Code: ", _LastError);
     }

   if(use_breakeven)
      break_even();
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
void              SendTelegramMessage(string msg)
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
      Print("NETWORK IS NOT CONNECTED, UNABLE TO SEND MESSAGE.");
      return;
     }

   if(StringLen(botTkn) == 0 || StringLen(chatID) == 0)   // Validate inputs
     {
      Print("ERROR: Telegram bot token or chat ID is missing.");
      return;
     }

// Send the web request to the Telegram API
   int send_res = WebRequest("POST", url, "", 10000, data, res, resHeaders);
// Check the response status of the web request
   if(send_res == 200)
     {
      // If the response status is 200 (OK), print a success message
      Print("ALERT SENT TO TELEGRAM SUCCESSFULLY");
     }
   else
      if(send_res == -1)
        {
         // If the response status is -1 (error), check the specific error code
         if(GetLastError() == 4014)
           {
            // If the error code is 4014, it means the Telegram API URL is not allowed in the terminal
            Print("PLEASE ADD THE ", TG_API_URL, " TO THE TERMINAL");
            return;
           }
         // Print a general error message if the request fails
         Print("UNABLE TO SEND ALERT TO TELEGRAM");
         return;
        }
      else
         if(send_res != 200)
           {
            // If the response status is not 200 or -1, print the unexpected response code and error code
            Print("UNEXPECTED RESPONSE ", send_res, " ERR CODE = ", GetLastError());
            return;
           }
  }

// Function
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
