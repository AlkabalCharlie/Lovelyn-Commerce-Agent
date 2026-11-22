"""Diagnose edge-tts WordBoundary stream."""
import asyncio
import edge_tts

async def main():
    c = edge_tts.Communicate("Hello world, this is a test.",
                             "en-US-AndrewMultilingualNeural")
    types = []
    async for chunk in c.stream():
        types.append(chunk["type"])
        if chunk["type"] == "WordBoundary":
            print("WB:", chunk["offset"], chunk["duration"], chunk["text"])
    print("chunk types seen:", set(types))

asyncio.run(main())
