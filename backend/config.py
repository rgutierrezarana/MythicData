import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    PROJECT_NAME: str = "MTG Card Explorer & Pricing Platform"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    
    # Base de datos: PostgreSQL por defecto, fallback automático a SQLite si no hay conexión
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB_MTG", "mtg_dw")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "airflow")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "airflow")
    
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{os.getenv('POSTGRES_USER', 'airflow')}:{os.getenv('POSTGRES_PASSWORD', 'airflow')}@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB_MTG', 'mtg_dw')}"
    )
    
    SQLITE_DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "mtg_explorer.db")
    
    # Rutas de datos Parquet para inicialización / auto-seeding
    DATA_DIR: str = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    LAKE_DIR: str = os.path.join(DATA_DIR, "lake")
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    # Entorno
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    ENABLE_TRACING: bool = os.getenv("ENABLE_TRACING", "true").lower() in ("true", "1", "yes")

    # Airflow & Observabilidad
    AIRFLOW_API_URL: str = os.getenv("AIRFLOW_API_URL", "http://airflow-webserver:8080/api/v1")
    AIRFLOW_WEB_URL: str = os.getenv("AIRFLOW_WEB_URL", "http://localhost:8080")
    AIRFLOW_USER: str = os.getenv("_AIRFLOW_WWW_USER_USERNAME", "admin")
    AIRFLOW_PASSWORD: str = os.getenv("_AIRFLOW_WWW_USER_PASSWORD", "admin")
    AIRFLOW_LOGS_DIR: str = os.getenv("AIRFLOW_LOGS_DIR", "/opt/airflow/logs")

    # Jaeger Tracing
    JAEGER_API_URL: str = os.getenv("JAEGER_API_URL", "http://jaeger:16686/api")
    JAEGER_UI_URL: str = os.getenv("JAEGER_UI_URL", "http://localhost:16686")

    class Config:
        case_sensitive = True


settings = Settings()
