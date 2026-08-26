import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.scholar_service import search_papers

async def main():
    try:
        results = await search_papers("brain computer interface autism dataset", 10)
        print(results)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
