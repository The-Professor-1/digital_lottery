"""
Test Redis connection
Run this: python test_redis.py
"""
import redis
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Connect to Redis
    r = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        decode_responses=True
    )
    
    # Test connection
    response = r.ping()
    
    if response:
        print("✅ Redis is working perfectly!")
        print(f"   Connected to: {os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', 6379)}")
        
        # Test set/get
        r.set('test_key', 'test_value')
        value = r.get('test_key')
        print(f"   Test write/read: {value}")
        r.delete('test_key')
        print("   ✅ All Redis operations working!")
    else:
        print("❌ Redis connection failed")
        
except redis.ConnectionError:
    print("❌ Cannot connect to Redis")
    print("   Make sure Redis server is running on port 6379")
except Exception as e:
    print(f"❌ Error: {e}")

