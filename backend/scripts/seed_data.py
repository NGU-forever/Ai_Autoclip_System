"""
backend/scripts/seed_data.py
----------------------------
该脚本不再写入任何默认初始数据。
保留入口仅用于兼容既有运维/部署流程。
"""


def insert_agents() -> None:
    print("Skip seeding agents: no default agent seed data configured.")


def insert_documents() -> None:
    print("Skip seeding documents: no default knowledge seed data configured.")


if __name__ == "__main__":
    insert_agents()
    insert_documents()
