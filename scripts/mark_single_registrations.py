from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Registration
from app.database import Base

DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def main():
    session = Session()
    regs = session.query(Registration).filter(Registration.promo_code == None).all()
    for reg in regs[:6]:
        reg.promo_code = "Pines1Player"
    session.commit()
    print(f"Updated {min(len(regs),6)} registrations")


if __name__ == "__main__":
    main()
