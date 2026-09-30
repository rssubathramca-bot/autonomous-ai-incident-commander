from .seed import seed_demo_data
from .session import SessionLocal, init_db


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        inserted = seed_demo_data(db)
    finally:
        db.close()

    if inserted:
        print("Initialized database and inserted Checkout Service demo data.")
    else:
        print("Database already contains the Checkout Service demo data.")


if __name__ == "__main__":
    main()
