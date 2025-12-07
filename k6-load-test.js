import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 100 },  // Ramp up to 100 users
    { duration: '1m', target: 100 },  // Stay at 100 users
    { duration: '30s', target: 200 }, // Ramp up to 200 users
    { duration: '1m', target: 200 },  // Stay at 200 users
    { duration: '30s', target: 400 }, // Ramp up to 400 users
    { duration: '1m', target: 400 },  // Stay at 400 users
    { duration: '30s', target: 0 },   // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests should be below 2s
    http_req_failed: ['rate<0.05'],     // Error rate should be less than 5%
    errors: ['rate<0.1'],               // Custom error rate
  },
};

// Base URL - change this to your app URL
const BASE_URL = __ENV.BASE_URL || 'https://markos-bingo.fly.dev';

// Test user tokens (optional - for authenticated endpoints)
// You can generate test tokens or use read-only endpoints
const TEST_TOKENS = __ENV.TEST_TOKENS ? __ENV.TEST_TOKENS.split(',') : [];

export default function () {
  // Test 1: Health check endpoint (read-only, safe)
  const healthRes = http.get(`${BASE_URL}/api/health/`);
  check(healthRes, {
    'health check status is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  // Test 2: Get current game (read-only, safe)
  const gameRes = http.get(`${BASE_URL}/api/games/current/`);
  check(gameRes, {
    'get current game status is 200': (r) => r.status === 200,
    'get current game response time < 2s': (r) => r.timings.duration < 2000,
    'game response has id': (r) => {
      try {
        const data = JSON.parse(r.body);
        return data.id !== undefined;
      } catch {
        return false;
      }
    },
  }) || errorRate.add(1);

  // Test 3: Get available cards (read-only, safe)
  if (gameRes.status === 200) {
    try {
      const gameData = JSON.parse(gameRes.body);
      if (gameData.id) {
        const cardsRes = http.get(`${BASE_URL}/api/games/${gameData.id}/available_cards/`);
        check(cardsRes, {
          'get available cards status is 200': (r) => r.status === 200,
          'available cards response time < 1s': (r) => r.timings.duration < 1000,
        }) || errorRate.add(1);
      }
    } catch (e) {
      // Ignore JSON parse errors
    }
  }

  // Test 4: Static files (read-only, safe)
  const staticRes = http.get(`${BASE_URL}/static/`);
  check(staticRes, {
    'static files status is 200 or 404': (r) => r.status === 200 || r.status === 404,
  }) || errorRate.add(1);

  // Random sleep between 1-3 seconds to simulate real user behavior
  sleep(Math.random() * 2 + 1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data),
  };
}

function textSummary(data, options) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;
  
  let summary = '\n';
  summary += `${indent}Test Summary\n`;
  summary += `${indent}============\n\n`;
  
  // HTTP metrics
  if (data.metrics.http_req_duration) {
    const duration = data.metrics.http_req_duration;
    summary += `${indent}HTTP Request Duration:\n`;
    summary += `${indent}  Average: ${duration.values.avg.toFixed(2)}ms\n`;
    summary += `${indent}  Min: ${duration.values.min.toFixed(2)}ms\n`;
    summary += `${indent}  Max: ${duration.values.max.toFixed(2)}ms\n`;
    summary += `${indent}  p95: ${duration.values['p(95)'].toFixed(2)}ms\n`;
    summary += `${indent}  p99: ${duration.values['p(99)'].toFixed(2)}ms\n\n`;
  }
  
  if (data.metrics.http_req_failed) {
    const failed = data.metrics.http_req_failed;
    summary += `${indent}HTTP Request Failed Rate: ${(failed.values.rate * 100).toFixed(2)}%\n\n`;
  }
  
  if (data.metrics.http_reqs) {
    const reqs = data.metrics.http_reqs;
    summary += `${indent}Total HTTP Requests: ${reqs.values.count}\n`;
    summary += `${indent}Requests per second: ${reqs.values.rate.toFixed(2)}\n\n`;
  }
  
  // Thresholds
  if (data.metrics.thresholds) {
    summary += `${indent}Thresholds:\n`;
    for (const [name, threshold] of Object.entries(data.metrics.thresholds)) {
      const status = threshold.ok ? '✓ PASS' : '✗ FAIL';
      summary += `${indent}  ${name}: ${status}\n`;
    }
  }
  
  return summary;
}

