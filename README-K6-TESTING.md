# K6 Load Testing Guide

This guide explains how to safely load test your Bingo application without affecting production data or state.

## ✅ Safety Guarantees

**k6 load testing is 100% safe** because:
1. **Read-only endpoints**: The test script only uses GET requests (read-only)
2. **No data modification**: No POST/PUT/DELETE requests that could change game state
3. **No authentication required**: Tests use public endpoints only
4. **No side effects**: Testing doesn't create users, games, or transactions

## 📋 Prerequisites

1. Install k6:
   ```bash
   # Windows (using Chocolatey)
   choco install k6
   
   # Or download from: https://k6.io/docs/getting-started/installation/
   ```

2. Verify installation:
   ```bash
   k6 version
   ```

## 🚀 Running Load Tests

### Option 1: Read-Only Test (Recommended - 100% Safe)

This test only uses GET endpoints and won't affect any game state:

```bash
# Test with default URL (markos-bingo.fly.dev)
k6 run k6-load-test-readonly.js

# Test with custom URL
k6 run -e BASE_URL=https://markos-bingo.fly.dev k6-load-test-readonly.js
```

### Option 2: Full Test (Includes Read Operations)

```bash
k6 run k6-load-test.js
```

## 📊 Test Scenarios

The test script includes three load scenarios:

1. **100 users** - Ramp up over 30s, maintain for 1 minute
2. **200 users** - Ramp up over 30s, maintain for 1 minute  
3. **400 users** - Ramp up over 30s, maintain for 1 minute
4. **Ramp down** - Gradually reduce to 0 users over 30s

## 📈 Understanding Results

The test measures:
- **Response times** (average, min, max, p95, p99)
- **Request rate** (requests per second)
- **Error rate** (should be < 5%)
- **Threshold compliance** (p95 < 2s, error rate < 5%)

## 🎯 What Gets Tested

### Read-Only Endpoints (Safe):
- ✅ `/api/health/` - Health check
- ✅ `/api/games/current/` - Get current game
- ✅ `/api/games/{id}/available_cards/` - Get available cards
- ✅ `/` - Frontend static files

### NOT Tested (To Keep Safe):
- ❌ Card selection (POST)
- ❌ Number marking (POST)
- ❌ Bingo claiming (POST)
- ❌ User registration
- ❌ Deposits/Withdrawals

## 🔧 Customization

### Change Load Levels

Edit the `stages` in the test file:

```javascript
stages: [
  { duration: '30s', target: 50 },   // Start with 50 users
  { duration: '1m', target: 50 },
  { duration: '30s', target: 100 },
  { duration: '1m', target: 100 },
  // ... etc
],
```

### Change Test Duration

Modify the `duration` values in stages to test for longer/shorter periods.

### Change Thresholds

Adjust performance expectations:

```javascript
thresholds: {
  http_req_duration: ['p(95)<1500'], // Stricter: 95% < 1.5s
  http_req_failed: ['rate<0.01'],    // Stricter: < 1% errors
},
```

## 📝 Output

Results are displayed in:
1. **Console** - Real-time summary
2. **summary.json** - Detailed JSON report

## ⚠️ Important Notes

1. **Production Safety**: These tests are read-only and won't affect your production app
2. **Rate Limiting**: If you have rate limiting, you may see some 429 errors (expected)
3. **Database Load**: Tests will increase database read load, but won't modify data
4. **Monitoring**: Watch your Fly.io dashboard during testing to monitor resource usage

## 🐛 Troubleshooting

### "Connection refused" errors
- Check if BASE_URL is correct
- Verify the app is running and accessible

### High error rates
- Check app logs: `fly logs --app markos-bingo`
- Verify database connection is stable
- Check if app is hitting memory limits

### Slow response times
- Check Fly.io machine resources
- Review database query performance
- Consider scaling up machines if needed

## 📊 Example Output

```
✓ health check status is 200
✓ get current game status is 200
✓ get current game response time < 2s
✓ game response has id
✓ get available cards status is 200
✓ available cards response time < 1s
✓ frontend loads status is 200

Test Summary
============

HTTP Request Duration:
  Average: 245.32ms
  Min: 45.12ms
  Max: 1234.56ms
  p95: 567.89ms
  p99: 890.12ms

HTTP Request Failed Rate: 0.12%

Total HTTP Requests: 15420
Requests per second: 42.33

Thresholds:
  http_req_duration: ✓ PASS
  http_req_failed: ✓ PASS
  errors: ✓ PASS
```

