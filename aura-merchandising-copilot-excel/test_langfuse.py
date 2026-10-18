
import os
from dotenv import load_dotenv
from langfuse import get_client

load_dotenv()

required = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
missing = [key for key in required if not os.getenv(key)]

if missing:
    print("Missing configuration:", ", ".join(missing))
    raise SystemExit(1)

try:
    client = get_client()

    with client.start_as_current_observation(
        as_type="span",
        name="aura-langfuse-verification",
        input={"test": "Aura Langfuse connection check"},
    ) as span:
        span.update(
            output={"status": "test completed"}
        )

    client.flush()
    print("Test observation submitted. Check Langfuse.")

except Exception as exc:
    print("LANGFUSE TEST FAILED:", type(exc).__name__, str(exc))
