#!/usr/bin/env python3
"""Simple test script to verify LLM connection and model."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from openai import OpenAI
import httpx

# Get API key from environment
api_key = os.environ.get("OPENAI_API_KEY", "")
if not api_key:
    print("ERROR: OPENAI_API_KEY environment variable not set")
    sys.exit(1)

# Model from config
model = "gpt-5-nano"

print(f"Testing OpenAI API connection...")
print(f"Model: {model}")
print(f"API Key: {api_key[:20]}...")

# Create client with proxy disabled
client = OpenAI(
    api_key=api_key,
    http_client=httpx.Client(trust_env=False, timeout=60.0)
)

try:
    # Test different parameter combinations to see what GPT-5-nano supports
    print("\nTesting parameter support...")
    
    # Test 1: No parameters (just model and messages)
    print("Test 1: Basic request (no max_tokens, no temperature)...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'test'"}],
        )
        print(f"  [SUCCESS] Basic request works")
    except Exception as e:
        print(f"  [FAILED] {type(e).__name__}: {str(e)[:100]}")
    
    # Test 2: With max_completion_tokens
    print("Test 2: With max_completion_tokens=10...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'test'"}],
            max_completion_tokens=10,
        )
        print(f"  [SUCCESS] max_completion_tokens works")
    except Exception as e:
        print(f"  [FAILED] {type(e).__name__}: {str(e)[:100]}")
    
    # Test 3: With max_tokens (should fail)
    print("Test 3: With max_tokens=10 (should fail)...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'test'"}],
            max_tokens=10,
        )
        print(f"  [UNEXPECTED] max_tokens worked (unexpected)")
    except Exception as e:
        print(f"  [EXPECTED] max_tokens failed: {type(e).__name__}")
    
    # Test 4: With temperature (should fail)
    print("Test 4: With temperature=0.0 (should fail)...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'test'"}],
            temperature=0.0,
        )
        print(f"  [UNEXPECTED] temperature worked (unexpected)")
    except Exception as e:
        print(f"  [EXPECTED] temperature failed: {type(e).__name__}")
    
    # Use the working combination for final test
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say 'Hello, world!' in one word."}],
        max_completion_tokens=10,
    )
    
    content = response.choices[0].message.content
    print(f"\n[SUCCESS]")
    print(f"Response: {content}")
    print(f"Model used: {response.model}")
    print(f"Finish reason: {response.choices[0].finish_reason}")
    
except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}")
    print(f"Message: {str(e)}")
    
    # Try to get more details
    if hasattr(e, 'response'):
        try:
            if hasattr(e.response, 'json'):
                error_detail = e.response.json()
                print(f"Details: {error_detail}")
        except:
            pass
    
    sys.exit(1)
