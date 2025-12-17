import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Construir la URL de la BD usando las variables de entorno
# Nota: "db" es el nombre del servicio en docker-compose
DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@db:5432/{os.getenv('POSTGRES_DB')}"

# Crear el motor de conexión
engine = create_engine(DATABASE_URL)

# Crear la sesión (la "fábrica" de conexiones)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para los modelos (tablas)
Base = declarative_base()

# Dependencia para obtener la DB en cada petición
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()