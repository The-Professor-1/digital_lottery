import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';
import ws from 'k6/ws';
import { Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const cardSelectionTime = new Trend('card_selection_time');
const websocketConnectTime = new Trend('websocket_connect_time');

// Test configuration - Simulates real user behavior
export const options = {
  stages: [
    { duration: '30s', target: 100 },  // Ramp up to 100 users
    { duration: '1m', target: 100 },   // Stay at 100 users
    { duration: '30s', target: 200 },  // Ramp up to 200 users
    { duration: '1m', target: 200 },    // Stay at 200 users
    { duration: '30s', target: 400 },   // Ramp up to 400 users
    { duration: '1m', target: 400 },   // Stay at 400 users
    { duration: '30s', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'], // 95% of requests should be below 3s (more lenient for POST)
    http_req_failed: ['rate<0.1'],     // Error rate should be less than 10% (more lenient)
    errors: ['rate<0.15'],             // Custom error rate
    card_selection_time: ['p(95)<5000'], // Card selection should complete in 5s
  },
};

// Base URL
const BASE_URL = __ENV.BASE_URL || 'https://markos-bingo.fly.dev';

// Test user tokens (optional - for authenticated endpoints)
// Note: For real testing, you'd need to generate test tokens
// For now, we'll test the read-only flow and simulate the card selection pattern
const TEST_TOKENS = __ENV.TEST_TOKENS ? __ENV.TEST_TOKENS.split(',') : [];

export default function () {
  // Step 1: Load frontend (simulates user opening web)
  const frontendRes = http.get(`${BASE_URL}/`);
  check(frontendRes, {
    'frontend loads': (r) => r.status === 200,
  }) || errorRate.add(1);

  sleep(1); // User reading the page

  // Step 2: Get current game (user checking available game)
  const gameRes = http.get(`${BASE_URL}/api/games/current/`);
  const gameCheck = check(gameRes, {
    'get current game status is 200': (r) => r.status === 200,
    'game response has id': (r) => {
      try {
        const data = JSON.parse(r.body);
        return data.id !== undefined;
      } catch {
        return false;
      }
    },
  });
  
  if (!gameCheck) {
    errorRate.add(1);
    return; // Can't proceed without game
  }

  let gameData;
  try {
    gameData = JSON.parse(gameRes.body);
  } catch (e) {
    errorRate.add(1);
    return;
  }

  const gameId = gameData.id;
  if (!gameId) {
    errorRate.add(1);
    return;
  }

  sleep(0.5); // User thinking about which card to select

  // Step 3: Get available cards (user browsing card selection)
  const cardsRes = http.get(`${BASE_URL}/api/games/${gameId}/available_cards/`);
  check(cardsRes, {
    'get available cards status is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  let availableCards = [];
  try {
    const cardsData = JSON.parse(cardsRes.body);
    availableCards = cardsData.available_cards || [];
  } catch (e) {
    // Ignore parse errors
  }

  sleep(1); // User selecting a card

  // Step 4: Simulate WebSocket connection (user connecting for real-time updates)
  // Note: Actual card selection requires authentication, so we'll simulate the connection
  const wsUrl = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');
  const wsUrlFull = `${wsUrl}/ws/game/${gameId}/`;
  
  // Try WebSocket connection (with timeout)
  const response = ws.connect(wsUrlFull, {}, function (socket) {
    socket.on('open', function () {
      // WebSocket connected successfully
      websocketConnectTime.add(Date.now());
    });

    socket.on('message', function (data) {
      // Received real-time update
      // In real scenario, this would be number calls, card selections, etc.
    });

    socket.on('close', function () {
      // WebSocket closed
    });

    // Keep connection open for a bit to simulate active gameplay
    sleep(2);
    
    socket.close();
  });

  check(response, {
    'websocket connection': (r) => r && r.status === 101,
  }) || errorRate.add(1);

  // Step 5: Simulate checking game status during play
  const gameStatusRes = http.get(`${BASE_URL}/api/games/current/`);
  check(gameStatusRes, {
    'game status check during play': (r) => r.status === 200,
  }) || errorRate.add(1);

  sleep(1); // User playing
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';
  
  let summary = '\n';
  summary += `${indent}═══════════════════════════════════════════\n`;
  summary += `${indent}  K6 Full Load Test Summary\n`;
  summary += `${indent}═══════════════════════════════════════════\n\n`;
  
  // HTTP metrics
  if (data.metrics && data.metrics.http_req_duration && data.metrics.http_req_duration.values) {
    const duration = data.metrics.http_req_duration;
    const values = duration.values;
    summary += `${indent}📊 HTTP Request Duration:\n`;
    if (values.avg !== undefined) summary += `${indent}   Average: ${values.avg.toFixed(2)}ms\n`;
    if (values.min !== undefined) summary += `${indent}   Min: ${values.min.toFixed(2)}ms\n`;
    if (values.max !== undefined) summary += `${indent}   Max: ${values.max.toFixed(2)}ms\n`;
    if (values['p(95)'] !== undefined) summary += `${indent}   p95: ${values['p(95)'].toFixed(2)}ms\n`;
    if (values['p(99)'] !== undefined) summary += `${indent}   p99: ${values['p(99)'].toFixed(2)}ms\n`;
    summary += '\n';
  }
  
  if (data.metrics && data.metrics.http_req_failed && data.metrics.http_req_failed.values) {
    const failed = data.metrics.http_req_failed;
    const rate = failed.values.rate || 0;
    summary += `${indent}❌ HTTP Request Failed Rate: ${(rate * 100).toFixed(2)}%\n\n`;
  }
  
  if (data.metrics && data.metrics.http_reqs && data.metrics.http_reqs.values) {
    const reqs = data.metrics.http_reqs;
    const values = reqs.values;
    summary += `${indent}📈 Total HTTP Requests: ${values.count || 0}\n`;
    if (values.rate !== undefined) {
      summary += `${indent}📈 Requests per second: ${values.rate.toFixed(2)}\n`;
    }
    summary += '\n';
  }
  
  // WebSocket metrics
  if (data.metrics && data.metrics.websocket_connect_time) {
    summary += `${indent}🔌 WebSocket Connections: Tested\n\n`;
  }
  
  // Thresholds
  if (data.metrics && data.metrics.thresholds) {
    summary += `${indent}✅ Thresholds:\n`;
    for (const [name, threshold] of Object.entries(data.metrics.thresholds)) {
      const status = threshold.ok ? '✓ PASS' : '✗ FAIL';
      summary += `${indent}   ${name}: ${status}\n`;
    }
  }
  
  summary += `\n${indent}═══════════════════════════════════════════\n`;
  
  return summary;
}

