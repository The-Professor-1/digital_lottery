import http from 'k6/http';
import { check, sleep } from 'k6';

// Quick test with just 10 users to verify everything works
export const options = {
  stages: [
    { duration: '10s', target: 10 },  // Ramp up to 10 users
    { duration: '20s', target: 10 },  // Stay at 10 users
    { duration: '10s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<5000'], // More lenient for quick test
    http_req_failed: ['rate<0.1'],     // Allow up to 10% errors for quick test
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://markos-bingo.fly.dev';

export default function () {
  // Test health endpoint
  const healthRes = http.get(`${BASE_URL}/api/health/`);
  check(healthRes, {
    'health check status is 200': (r) => r.status === 200,
  });

  // Test get current game
  const gameRes = http.get(`${BASE_URL}/api/games/current/`);
  check(gameRes, {
    'get current game status is 200': (r) => r.status === 200,
  });

  sleep(1);
}

