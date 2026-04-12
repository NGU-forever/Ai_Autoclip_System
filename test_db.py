import asyncio
import asyncpg
import os

async def main():
    try:
        conn = await asyncpg.connect('postgresql://b2b_user:b2b_password@127.0.0.1:5432/b2b_db')
        
        # Check accounts table schema
        schema = await conn.fetch("""
        SELECT column_name, data_type, column_default 
        FROM information_schema.columns 
        WHERE table_name = 'accounts';
        """)
        
        print("Accounts Table Schema:")
        for row in schema:
            print(f"- {row['column_name']}: {row['data_type']} (default: {row['column_default']})")
            
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
