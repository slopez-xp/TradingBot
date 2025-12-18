from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# Construir la URL de la BD usando el objeto de configuración centralizado
# Nota: "postgres_host" tiene por defecto "db", que es el nombre del servicio en docker-compose
DATABASE_URL = (
    f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

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