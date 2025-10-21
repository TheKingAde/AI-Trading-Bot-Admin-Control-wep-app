# EA Integration Guide

## Overview
This document explains how Expert Advisors (EAs) can integrate with the Bot Dashboard to send data and enable multi-account monitoring.

## Multi-Account Architecture

The dashboard now supports monitoring multiple licensed EA instances simultaneously. Each EA is identified by its unique license key, and the admin can switch between accounts to view specific data.

### Database Schema

Each data table now includes a `license_key` field to link data to specific EA instances:
- `accounts` - Account balance, equity, win rate per license
- `trades` - Trade history per license
- `performance` - Performance metrics per pair per license
- `ai_insights` - AI-generated insights per license

## Public API Endpoints (No Authentication Required)

These endpoints are called by EAs to send data to the dashboard.

### 1. Check License Validity
```http
GET /api/license/check?key=YOUR_LICENSE_KEY
```

**Response:**
```json
{
  "key": "ABC123...",
  "status": "active",
  "expires_at": "2025-12-31T23:59:59",
  "name": "John Doe"
}
```

### 2. Send Account Data
```http
POST /api/account_data
Content-Type: application/json

{
  "license_key": "YOUR_LICENSE_KEY",
  "balance": 10000.50,
  "equity": 10250.75,
  "win_rate": 0.65
}
```

**Response:**
```json
{
  "status": "stored"
}
```

### 3. Send Trade History
```http
POST /api/trade_history
Content-Type: application/json

{
  "license_key": "YOUR_LICENSE_KEY",
  "trades": [
    {
      "pair": "EURUSD",
      "lots": 0.1,
      "direction": "BUY",
      "result": 15.50,
      "opened_at": "2025-10-20T10:30:00",
      "closed_at": "2025-10-20T14:45:00",
      "ai_confidence": 0.85
    },
    {
      "pair": "GBPUSD",
      "lots": 0.2,
      "direction": "SELL",
      "result": -5.20,
      "opened_at": "2025-10-20T11:00:00",
      "closed_at": null,
      "ai_confidence": 0.72
    }
  ]
}
```

**Response:**
```json
{
  "status": "trades stored",
  "count": 2
}
```

### 4. Send Performance Data
```http
POST /api/performance
Content-Type: application/json

{
  "license_key": "YOUR_LICENSE_KEY",
  "performance": [
    {
      "pair": "EURUSD",
      "win_rate": 0.68,
      "drawdown": 0.15,
      "trades": 45
    },
    {
      "pair": "GBPUSD",
      "win_rate": 0.62,
      "drawdown": 0.22,
      "trades": 38
    }
  ]
}
```

**Response:**
```json
{
  "status": "performance stored",
  "count": 2
}
```

### 5. Send AI Insights
```http
POST /api/ai_insights
Content-Type: application/json

{
  "license_key": "YOUR_LICENSE_KEY",
  "insights": [
    "EURUSD momentum strengthening near support.",
    "GBPUSD shows divergence; consider reduced risk.",
    "USDJPY range-bound; wait for breakout confirmation."
  ]
}
```

**Response:**
```json
{
  "status": "insights stored",
  "count": 3
}
```

## Admin API Endpoints (Authentication Required)

These endpoints are used by the dashboard frontend and require JWT authentication.

### Get Live Trades
```http
GET /api/trade_data/live?license_key=YOUR_LICENSE_KEY
Authorization: Bearer <JWT_TOKEN>
```

### Get Account Stats
```http
GET /api/account_stats?license_key=YOUR_LICENSE_KEY
Authorization: Bearer <JWT_TOKEN>
```

### Get Performance Data
```http
GET /api/performance?license_key=YOUR_LICENSE_KEY
Authorization: Bearer <JWT_TOKEN>
```

### Get AI Insights
```http
GET /api/ai_insights?license_key=YOUR_LICENSE_KEY
Authorization: Bearer <JWT_TOKEN>
```

## Integration Workflow

### Step 1: EA Initialization
1. EA reads its license key from configuration
2. EA calls `/api/license/check?key=...` to verify license validity
3. If license is valid and active, proceed to Step 2
4. If license is invalid/expired, EA should disable trading

### Step 2: Periodic Data Transmission
EA should send data at regular intervals:

**Every 5 minutes:**
- Send current account data (balance, equity, win_rate)
- Send open trades with AI confidence

**Every 30 minutes:**
- Send AI insights (market analysis, trading signals)

**On trade close:**
- Update trade history with closed trade data

**Daily (or after significant changes):**
- Send updated performance metrics per pair

### Step 3: Dashboard Viewing
1. Admin logs into dashboard
2. Selects account from dropdown (shows all active licenses)
3. Dashboard displays data for selected license:
   - Account Stats (Balance, Equity, Win Rate)
   - Live Trades with AI confidence
   - Performance by Pair (chart and table)
   - AI Insights

## MQL5 Integration Example

```mql5
#define API_URL "http://your-server:8000/api"
#define LICENSE_KEY "YOUR_LICENSE_KEY"

// Send account data
void SendAccountData() {
   string url = API_URL + "/account_data";
   
   string json = StringFormat(
      "{\"license_key\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"win_rate\":%.2f}",
      LICENSE_KEY,
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY),
      CalculateWinRate()
   );
   
   char data[];
   StringToCharArray(json, data, 0, StringLen(json));
   
   char result[];
   string headers = "Content-Type: application/json\r\n";
   
   int res = WebRequest("POST", url, headers, 5000, data, result, headers);
   
   if(res == 200) {
      Print("Account data sent successfully");
   }
}

// Send trade data
void SendTradeData(ulong ticket) {
   if(!PositionSelectByTicket(ticket)) return;
   
   string url = API_URL + "/trade_history";
   
   string json = StringFormat(
      "{\"license_key\":\"%s\",\"trades\":[{\"pair\":\"%s\",\"lots\":%.2f,\"direction\":\"%s\",\"result\":%.2f,\"ai_confidence\":%.2f}]}",
      LICENSE_KEY,
      PositionGetString(POSITION_SYMBOL),
      PositionGetDouble(POSITION_VOLUME),
      PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "BUY" : "SELL",
      PositionGetDouble(POSITION_PROFIT),
      GetAIConfidence()
   );
   
   // Send request...
}

// Check license validity
bool CheckLicense() {
   string url = API_URL + "/license/check?key=" + LICENSE_KEY;
   
   char result[];
   string headers = "";
   
   int res = WebRequest("GET", url, headers, 5000, NULL, result, headers);
   
   if(res == 200) {
      string response = CharArrayToString(result);
      // Parse JSON and check if status is "active"
      return StringFind(response, "\"status\":\"active\"") >= 0;
   }
   
   return false;
}
```

## Important Notes

1. **License Key Security**: Store license keys securely in EA configuration
2. **Rate Limiting**: Don't send data too frequently (follow recommended intervals)
3. **Error Handling**: Always handle API errors gracefully
4. **Data Validation**: Validate data before sending to avoid errors
5. **Network Issues**: Implement retry logic for failed requests
6. **Testing**: Use test license keys during development

## Support

For issues or questions about EA integration, contact the system administrator.
